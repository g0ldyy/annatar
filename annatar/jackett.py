import asyncio
import os
import re
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Optional

import aiohttp
import structlog
from prometheus_client import Histogram
from structlog.contextvars import bound_contextvars

from annatar import human, instrumentation
from annatar.database import db
from annatar.debrid import magnet
from annatar.jackett_models import (
    MOVIES,
    SERIES,
    Indexer,
    ScoredTorrent,
    SearchQuery,
    SearchResult,
    SearchResults,
)

log = structlog.get_logger(__name__)

MAX_RESULTS_PER_INDEXER = int(os.environ.get("JACKETT_MAX_RESULTS", 50))
JACKETT_TIMEOUT = int(os.environ.get("JACKETT_TIMEOUT", 5))


REQUEST_DURATION = Histogram(
    name="jackett_request_duration_seconds",
    documentation="Duration of Jackett requests in seconds",
    labelnames=["method", "indexer", "status", "cached"],
    registry=instrumentation.registry(),
)


async def get_indexers() -> list[Indexer]:
    return Indexer.all()


async def search_indexer(
    search_query: SearchQuery,
    jackett_url: str,
    jackett_api_key: str,
    indexer: str,
    cache_key: str,
    imdb: int | None = None,
) -> list[str]:
    suffix: str = "" if search_query.type == "series" else f"{search_query.year}"
    sanitized_name: str = re.sub(r"\W", " ", search_query.name)
    category: str = str(MOVIES.id if search_query.type == "movie" else SERIES.id)

    torrents: list[str] = []
    try:
        raw_results: list[SearchResult] = await execute_search(
            jackett_api_key=jackett_api_key,
            jackett_url=jackett_url,
            indexer=indexer,
            params={
                "Category": category,
                "Query": f"{sanitized_name} {suffix}",
                "Tracker[]": indexer,
            },
        )
    except JackettSearchError:
        # if the search fails, we will cache the empty result for a short time
        # to avoid hammering the indexer
        # Don't log because we already logged in execute_search
        return torrents

    search_results: list[SearchResult] = sorted(
        raw_results,
        key=lambda r: r.Seeders,
        reverse=True,
    )

    tasks = [
        asyncio.create_task(map_matched_result(result=result, search_query=search_query, imdb=imdb))
        for result in search_results
    ]

    scored_torrents: list[ScoredTorrent] = []
    for i, task in enumerate(asyncio.as_completed(tasks)):
        torrent: ScoredTorrent | None = await task
        if torrent and torrent.score > 0:
            if await db.unique_list_add(
                name=cache_key,
                item=torrent.info_hash,
                score=torrent.score,
            ):
                log.info("added scored torrent to unique list", torrent=torrent)
                scored_torrents.append(torrent)
                if i > MAX_RESULTS_PER_INDEXER:
                    # back off once we have what we need
                    # doing this here so that the loop will continue for tasks
                    # that have already completed
                    for t in tasks:
                        if not t.done():
                            t.cancel()

    prioritized_list: list[str] = [
        t.info_hash for t in sorted(list(scored_torrents), key=lambda t: t.score, reverse=True)
    ]

    log.info("found torrents in indexer", tracker=indexer, count=len(prioritized_list))
    return prioritized_list


async def search_indexers(
    search_query: SearchQuery,
    jackett_url: str,
    jackett_api_key: str,
    max_results: int,
    imdb: int | None = None,
    timeout: int = 60,
    indexers: list[Indexer] = Indexer.all(),
) -> AsyncGenerator[str, None]:
    log.info("searching indexers", indexers=indexers)
    cache_key: str = f"jackett:search:tt{imdb}"
    torrents: list[str] = await db.unique_list_get(cache_key)

    if len(torrents) >= MAX_RESULTS_PER_INDEXER:
        log.info("found enough torrents in cache", count=len(torrents))
        for i, info_hash in enumerate(torrents):
            yield info_hash
            if i >= max_results:
                return
        return

    # the list is not long enough, we need to search for more
    tasks = [
        asyncio.create_task(
            search_indexer(
                search_query=search_query,
                jackett_url=jackett_url,
                jackett_api_key=jackett_api_key,
                imdb=imdb,
                indexer=indexer.id,
                cache_key=cache_key,
            )
        )
        for indexer in indexers
        if indexer.supports(search_query.type)
    ]

    await gather_indexer_results(tasks)

    # now get the prioritized list from the cache because we can't reprioritize
    # now that we lost the scores. Redis will keep the order for us
    prioritized_list: list[str] = await db.unique_list_get(cache_key)

    # cache for longer if we found enough data
    ttl: timedelta = (
        timedelta(minutes=15)
        if len(prioritized_list) < MAX_RESULTS_PER_INDEXER
        else timedelta(hours=6)
    )

    await db.set_ttl(cache_key, ttl)
    for i, info_hash in enumerate(prioritized_list):
        yield info_hash
        if i >= max_results:
            return

    log.info("finished searching indexers", count=len(prioritized_list))


async def gather_indexer_results(tasks: list[asyncio.Task[list[str]]]):
    info_hashes: dict[str, bool] = {}
    for task in asyncio.as_completed(tasks):
        indexer_results: list[str] = await task
        for info_hash in indexer_results[:MAX_RESULTS_PER_INDEXER]:
            if not info_hash:
                continue
            if info_hash in info_hashes:
                continue
            info_hashes[info_hash] = True
            if len(info_hashes) >= MAX_RESULTS_PER_INDEXER:
                log.info("found enough torrents", count=len(info_hashes))
                return


class JackettSearchError(Exception):
    def __init__(self, message: str, status: int | None, cause: Exception | None):
        self.message = message
        self.status = status
        self.cause = cause


async def execute_search(
    jackett_url: str,
    jackett_api_key: str,
    indexer: str,
    params: dict[str, Any],
) -> list[SearchResult]:
    start_time = datetime.now()
    response_status: int = 0
    cached_response: bool = False
    try:
        url: str = f"{jackett_url}/api/v2.0/indexers/all/results"
        with bound_contextvars(
            search_params=params.copy(),
            url=url,
            indexer=indexer,
        ):
            params["apikey"] = jackett_api_key
            async with aiohttp.ClientSession() as session:
                log.info("searching jackett")
                try:
                    async with session.get(
                        url=url,
                        params=params,
                        timeout=JACKETT_TIMEOUT,
                        headers={"Accept": "application/json"},
                    ) as response:
                        response_status = response.status
                        if response.status != 200:
                            log.error(
                                "jacket search failed",
                                status=response.status,
                                reason=response.reason,
                                body=await response.text(),
                                exc_info=True,
                            )
                            return []
                        response_json = await response.json()
                except TimeoutError as e:
                    log.error("jacket search timeout", timeout=JACKETT_TIMEOUT)
                    raise JackettSearchError(
                        message="jackett search timeout",
                        status=response_status,
                        cause=e,
                    )
                except Exception as err:
                    log.error("jacket search error", exc_info=err)
                    raise JackettSearchError(
                        message="jackett search error",
                        status=response_status,
                        cause=err,
                    )

        res: SearchResults = SearchResults(
            Results=[SearchResult(**result) for result in response_json["Results"]]
        )
        return res.Results
    finally:
        status = f"{response_status // 100}xx"
        REQUEST_DURATION.labels(
            method="indexer_search",
            indexer=indexer,
            status=status,
            cached=cached_response,
        ).observe(
            amount=(datetime.now() - start_time).total_seconds(),
            exemplar={"category": params.get("Category", ""), "query": params.get("Query", "")},
        )


async def map_matched_result(
    result: SearchResult,
    search_query: SearchQuery,
    imdb: int | None,
) -> ScoredTorrent | None:
    if imdb and result.Imdb and result.Imdb != imdb:
        log.info(
            "skipping mismatched IMDB",
            wanted=imdb,
            got=result.Imdb,
        )
        return None

    match_score: int = human.score_name(search_query, result.Title)
    if match_score <= 0:
        log.info(
            "torrent scored too low",
            title=result.Title,
            match_score=match_score,
            wanted=search_query,
        )
        return None

    if search_query.episode:
        episode: int | None = human.find_episode(result.Title)
        if episode and episode != int(search_query.episode):
            log.info(
                "skipping mismatched episode",
                wanted=search_query.episode,
                got=episode,
            )
            return None

    info_hash: str | None = (
        result.InfoHash.upper()
        if result.InfoHash
        else (
            await resolve_magnet_link(
                guid=result.Guid,
                link=result.Link,
            )
            if result.Link and result.Link.startswith("http")
            else None
        )
    )

    if info_hash:
        return ScoredTorrent(info_hash=info_hash, score=match_score)
    return None


async def resolve_magnet_link(guid: str, link: str) -> str | None:
    """
    Jackett sometimes does not have a magnet link but a local URL that
    redirects to a magnet link. This will not work if adding to RD and
    Jackett is not publicly hosted. Most of the time we can resolve it
    locally. If not we will just pass it along to RD anyway
    """
    if link.startswith("magnet"):
        return magnet.parse_magnet_link(link)

    start_time = datetime.now()
    response_status: int = 200
    cached_response: bool = False
    try:
        cache_key: str = f"jackett:magnet:{guid}"
        info_hash: Optional[str] = await db.get(cache_key)
        if info_hash:
            cached_response = True
            return info_hash

        log.info("magnet resolve: following redirect", guid=guid, link=link)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                link, allow_redirects=False, timeout=JACKETT_TIMEOUT
            ) as response:
                response_status = response.status
                if response.status == 302:
                    if location := response.headers.get("Location", ""):
                        info_hash = magnet.parse_magnet_link(location)
                        log.info("magnet resolve: found redirect", guid=guid, info_hash=info_hash)
                        await db.set(cache_key, info_hash, ttl=timedelta(weeks=8))
                        return info_hash
                    return None
                else:
                    log.info("magnet resolve: no redirect found", guid=guid, status=response.status)
                    return None
    except TimeoutError:
        log.error("magnet resolve: timeout", guid=guid)
        return None
    except Exception as err:
        log.error("magnet resolve error", exc_info=err)
        return None
    finally:
        status = f"{response_status // 100}xx"
        REQUEST_DURATION.labels(
            method="magnet_resolve",
            indexer=None,
            status=status,
            cached=cached_response,
        ).observe(
            amount=(datetime.now() - start_time).total_seconds(),
        )
