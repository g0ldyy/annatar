import asyncio
import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional

import aiohttp
import structlog
from prometheus_client import Histogram
from structlog.contextvars import bound_contextvars

from annatar import instrumentation
from annatar.database import db
from annatar.debrid import magnet
from annatar.jackett_models import (
    MOVIES,
    SERIES,
    ScoredTorrent,
    SearchQuery,
    SearchResult,
    SearchResults,
)
from annatar.torrent import Torrent

log = structlog.get_logger(__name__)


JACKETT_URL: str = os.environ.get("JACKETT_URL", "http://localhost:9117")
JACKETT_API_KEY: str = os.environ.get("JACKETT_API_KEY", "")

JACKETT_MAX_RESULTS = int(os.environ.get("JACKETT_MAX_RESULTS", 10))
JACKETT_TIMEOUT = int(os.environ.get("JACKETT_TIMEOUT", 6))
SEARCH_TTL = timedelta(weeks=1)
JACKETT_CACHE_MINUTES = timedelta(minutes=int(os.environ.get("JACKETT_CACHE_MINUTES", 15)))

JACKETT_INDEXERS_LIST: list[str] = os.environ.get(
    "JACKETT_INDEXERS",
    "yts,eztv,kickasstorrents-ws,thepiratebay,therarbg,torrentgalaxy,bitsearch,limetorrents,badasstorrents",
).split(",")


REQUEST_DURATION = Histogram(
    name="jackett_request_duration_seconds",
    documentation="Duration of Jackett requests in seconds",
    labelnames=["method", "indexer", "status", "cached"],
    registry=instrumentation.registry(),
)


async def get_indexers() -> list[str]:
    return JACKETT_INDEXERS_LIST


async def search_indexer(
    search_query: SearchQuery,
    indexer: str,
    queue: asyncio.Queue[ScoredTorrent],
    stop: asyncio.Event,
):
    """
    Search a single indexer for torrents and insert them into the unique list
    by score
    """
    sanitized_name: str = re.sub(r"\W", " ", search_query.name)
    category: str = str(MOVIES.id if search_query.type == "movie" else SERIES.id)
    params = (
        {
            "Category": category,
            "Query": f"{sanitized_name}",
            "Tracker[]": indexer,
        }
        if search_query.type == "series"
        else {
            "t": "movie",
            "imdbid": search_query.imdb_id,
            "Tracker[]": indexer,
        }
    )

    log.debug("searching indexer", indexer=indexer, query=search_query.imdb_id)
    try:
        raw_results: list[SearchResult] = await execute_search(
            indexer=indexer,
            params=params,
        )
    except JackettSearchError:
        # Don't log because we already logged in execute_search
        # XXX need to set some kind of indicator to do backoffs on this indexer
        # if it fails too many times
        # XXX Also need to cache empty results for a period of time
        return

    search_results: list[SearchResult] = sorted(
        raw_results,
        key=lambda r: r.Seeders,
        reverse=True,
    )

    tasks = [
        asyncio.create_task(
            map_matched_results(
                result=result,
                search_query=search_query,
                queue=queue,
            ),
            name=f"map_matched_results:{result.Title}",
        )
        for result in search_results
    ]

    all_tasks = asyncio.gather(*tasks)
    stop_task = asyncio.create_task(stop.wait())
    done, pending = await asyncio.wait(
        {all_tasks, stop_task},
        timeout=JACKETT_TIMEOUT,
        return_when=asyncio.FIRST_COMPLETED,
    )

    if stop_task in done:
        log.debug("search cancelled", indexer=indexer)
        if not all_tasks.done():
            all_tasks.cancel()
        all([task.cancel() for task in tasks if not task.done()])
    else:
        log.debug("search finished", indexer=indexer)


async def search_indexers(
    search_query: SearchQuery,
    indexers: list[str],
) -> list[str]:
    log.info("searching indexers", indexers=indexers)

    cache_key: str = f"jackett:search:{search_query.imdb_id}"
    if search_query.type == "series":
        cache_key += f":{search_query.season}:{search_query.episode}"
    cache_key += ":torrents"

    results = set(s.value for s in await db.unique_list_get_scored(cache_key, limit_per_score=5))
    if len(results) >= JACKETT_MAX_RESULTS:
        log.info(
            "found enough torrents for this release in cache",
            count=len(results),
            cache_key=cache_key,
        )
        # reset the TTL for this key since it was recently used
        await db.set_ttl(cache_key, ttl=SEARCH_TTL)
        return list(results)

    ttl = await db.ttl(cache_key)
    age: float = SEARCH_TTL.total_seconds() - ttl
    if age <= JACKETT_CACHE_MINUTES.total_seconds():
        log.debug("results are fresh", key=cache_key, age=timedelta(seconds=age))
        return list(results)

    log.debug("Not enough items in cache. Searching indexers", imdb=search_query.imdb_id)
    queue: asyncio.Queue[ScoredTorrent] = asyncio.Queue()
    stop: asyncio.Event = asyncio.Event()
    tasks = [
        asyncio.create_task(
            search_indexer(
                search_query=search_query,
                indexer=indexer,
                queue=queue,
                stop=stop,
            ),
            name=f"search_indexer:{indexer}",
        )
        for indexer in indexers
    ]
    log.debug("created search tasks", count=len(tasks))

    end_time = datetime.now() + timedelta(seconds=JACKETT_TIMEOUT)
    while True:
        if all(task.done() for task in tasks) and queue.empty():
            log.debug("all search tasks done and queue empty")
            break
        try:
            scored_torrent: ScoredTorrent = await asyncio.wait_for(
                queue.get(),
                timeout=(end_time - datetime.now()).total_seconds(),
            )

            if scored_torrent.torrent.info_hash in results:
                log.debug("already have this torrent", torrent=scored_torrent.torrent.title)
                continue

            log.debug("got scored torrent", torrent=scored_torrent.torrent.title, have=len(results))
            results.add(scored_torrent.torrent.info_hash)

            await db.unique_list_add(
                cache_key,
                scored_torrent.torrent.info_hash,
                scored_torrent.score,
            )

            await db.set(
                f"torrent:{scored_torrent.torrent.info_hash}:name",
                scored_torrent.torrent.raw_title,
                # do not expire these. Torrent title is not going to change
            )

            if len(results) >= JACKETT_MAX_RESULTS:
                log.info("found enough torrents", count=len(results))
                stop.set()
                break
            else:
                log.debug("still need more torrents", have=len(results), want=JACKETT_MAX_RESULTS)
        except asyncio.TimeoutError:
            log.info("search timed out", timeout=JACKETT_TIMEOUT)
            stop.set()
            break

    log.info("finished searching indexers", found=len(results))

    if len(results) > 0:
        await db.set_ttl(cache_key, ttl=SEARCH_TTL)

    # retrieve them again because the scores and order might have changed after
    # adding more results
    return [item for item in await db.unique_list_get(cache_key)]


class JackettSearchError(Exception):
    def __init__(self, message: str, status: int | None, cause: Exception | None):
        self.message = message
        self.status = status
        self.cause = cause


async def execute_search(
    indexer: str,
    params: dict[str, Any],
) -> list[SearchResult]:
    start_time = datetime.now()
    response_status: int = 0
    cached_response: bool = False
    try:
        cache_key = f"jackett:search:{indexer}:{params}"
        if cached := await db.get_model(cache_key, SearchResults):
            log.info("search result cached", indexer=indexer, params=params)
            cached_response = True
            return cached.Results

        url: str = f"{JACKETT_URL}/api/v2.0/indexers/all/results"
        search_params = params.copy()
        with bound_contextvars(
            search_params=search_params,
            url=url,
            indexer=indexer,
        ):
            params["apikey"] = JACKETT_API_KEY
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
        await db.set_model(cache_key, res, ttl=JACKETT_CACHE_MINUTES)
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


async def map_matched_results(
    result: SearchResult,
    search_query: SearchQuery,
    queue: asyncio.Queue[ScoredTorrent],
):
    imdb_id: int = int(search_query.imdb_id.replace("tt", ""))
    if result.Imdb and result.Imdb != imdb_id:
        log.info(
            "skipping mismatched IMDB",
            wanted=search_query.imdb_id,
            got=result.Imdb,
        )
        return

    torrent: Torrent = Torrent.parse_title(title=result.Title)

    match_score: int = torrent.score_with(
        title=search_query.name,
        year=search_query.year,
        season=int(search_query.season) if search_query.season else 0,
        episode=int(search_query.episode) if search_query.episode else 0,
    )
    if match_score <= 0:
        log.debug(
            "torrent scored too low",
            title=result.Title,
            score=match_score,
            match_score=match_score,
            wanted=search_query,
        )
        return

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
        torrent.info_hash = info_hash
        log.debug("torrent scored well", title=result.Title, match_score=match_score)
        await queue.put(ScoredTorrent(torrent=torrent, score=match_score))


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

        log.debug("magnet resolve: following redirect", guid=guid, link=link)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                link, allow_redirects=False, timeout=JACKETT_TIMEOUT
            ) as response:
                response_status = response.status
                if response.status == 302:
                    if location := response.headers.get("Location", ""):
                        info_hash = magnet.parse_magnet_link(location)
                        log.debug(
                            "magnet resolve: found redirect", info_hash=info_hash, location=location
                        )
                        await db.set(cache_key, info_hash, ttl=timedelta(weeks=8))
                        return info_hash
                    return None
                else:
                    log.warn("magnet resolve: no redirect found", guid=guid, status=response.status)
                    return None
    except TimeoutError:
        log.warn("magnet resolve: timeout")
        return None
    except asyncio.exceptions.CancelledError:
        log.debug("magnet resolve: cancelled")
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
