import asyncio
import os
import re
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import structlog
from prometheus_client import Histogram
from structlog.contextvars import bound_contextvars

from annatar import instrumentation
from annatar.database import db, odm
from annatar.jackett_models import (
    MOVIES,
    SERIES,
    SearchQuery,
    SearchResult,
    SearchResults,
)
from annatar.pubsub.events import TorrentAdded, TorrentSearchCriteria, TorrentSearchResult
from annatar.torrent import Category

log = structlog.get_logger(__name__)


JACKETT_URL: str = os.environ.get("JACKETT_URL", "http://localhost:9117")
JACKETT_API_KEY: str = os.environ.get("JACKETT_API_KEY", "")

JACKETT_MAX_RESULTS = int(os.environ.get("JACKETT_MAX_RESULTS", 100))
JACKETT_TIMEOUT = int(os.environ.get("JACKETT_TIMEOUT", 6))
API_SEARCH_TIMEOUT = int(os.environ.get("API_SEARCH_TIMEOUT", 10))
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
            process_search_results(
                result=result,
                search_query=search_query,
            ),
            name=f"process_search_results:{search_query.imdb_id}:{i}",
        )
        for i, result in enumerate(search_results[:JACKETT_MAX_RESULTS])
    ]

    await asyncio.gather(*tasks)
    log.debug("search finished", indexer=indexer)


async def search_indexers(
    search_query: SearchQuery,
    indexers: list[str],
    resolutions: list[str],
) -> list[str]:
    log.info("searching indexers", indexers=indexers)

    results = await odm.list_torrents(
        imdb=search_query.imdb_id,
        season=search_query.season,
        episode=search_query.episode,
        resolutions=resolutions,
    )
    cache_key: str = odm.Keys.torrents(
        imdb=search_query.imdb_id,
        season=search_query.season,
        episode=search_query.episode,
    )
    if len(results) >= JACKETT_MAX_RESULTS:
        log.info("found enough torrents for this release in cache", count=len(results))
        await db.set_ttl(cache_key, SEARCH_TTL)
        return list(results)

    ttl = await db.ttl(cache_key)
    age: float = SEARCH_TTL.total_seconds() - ttl
    multiplier = max(5, datetime.now().year - search_query.year)
    min_cache_time = JACKETT_CACHE_MINUTES * multiplier
    if age <= min_cache_time.total_seconds():
        log.debug("results are fresh", key=cache_key, age=timedelta(seconds=age))
        return results

    if len(results) > 0:
        log.debug("torrents are stale, refreshing", imdb=search_query.imdb_id)
        return results

    log.debug("no results in cache, searching indexers", imdb=search_query.imdb_id)

    # offload to the background
    asyncio.create_task(offload_searches(search_query=search_query, indexers=indexers))
    if search_query.episode:
        without_episode = search_query.copy()
        without_episode.episode = None
        asyncio.create_task(offload_searches(search_query=without_episode, indexers=indexers))

    try:
        new_torrents = await asyncio.wait_for(
            asyncio.create_task(
                poll_new_torrents(
                    imdb=search_query.imdb_id,
                    season=search_query.season,
                    episode=search_query.episode,
                    limit=JACKETT_MAX_RESULTS,
                )
            ),
            timeout=API_SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        log.debug("search timeout", imdb=search_query.imdb_id, timeout=API_SEARCH_TIMEOUT)

    new_torrents = await odm.list_torrents(
        imdb=search_query.imdb_id,
        season=search_query.season,
        episode=search_query.episode,
        resolutions=resolutions,
    )
    results.extend(new_torrents)
    return list(set(results))


async def poll_new_torrents(
    imdb: str,
    season: int | None,
    episode: int | None,
    limit: int = JACKETT_MAX_RESULTS,
):
    log.debug("polling for new torrents", imdb=imdb, season=season, episode=episode)
    count = 0
    async for torrent in TorrentAdded.listen():
        log.debug("got new torrent", torrent=torrent)
        if torrent.imdb == imdb and torrent.season == season and torrent.episode == episode:
            count += 1
            if count >= limit:
                break


async def offload_searches(
    search_query: SearchQuery,
    indexers: list[str],
):
    tasks = [
        asyncio.create_task(
            search_indexer(
                search_query=search_query,
                indexer=indexer,
            ),
            name=f"search_indexer:{indexer}:{search_query.imdb_id}",
        )
        for indexer in indexers
    ]
    log.debug("created search tasks", count=len(tasks))
    await asyncio.gather(*tasks)
    log.info("finished searching indexers")


class JackettSearchError(Exception):
    def __init__(self, message: str, status: int | None):
        self.message = message
        self.status = status


async def execute_search(
    indexer: str,
    params: dict[str, Any],
) -> list[SearchResult]:
    start_time = datetime.now()
    response_status: int = 0
    cached_response: bool = False
    try:
        cache_key = f"jackett:search:{indexer}:" + ":".join(params.values())
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
                    ) from e
                except Exception as err:
                    log.error("jacket search error", exc_info=err)
                    raise JackettSearchError(
                        message="jackett search error",
                        status=response_status,
                    ) from err

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


async def process_search_results(
    result: SearchResult,
    search_query: SearchQuery,
):
    criterna = TorrentSearchCriteria(
        category=Category(search_query.type),
        imdb=search_query.imdb_id,
        season=int(search_query.season) if search_query.season else 0,
        episode=int(search_query.episode) if search_query.episode else 0,
        year=search_query.year,
        query=search_query.name,
    )
    link = result.MagnetUri or result.Link
    if not link:
        log.error("no magnet link found", result=result)
        return

    msg = TorrentSearchResult(
        search_criteria=criterna,
        info_hash=result.InfoHash or "",
        title=result.Title,
        guid=result.Guid,
        imdb=f"tt{int(result.Imdb):07d}" if result.Imdb else "",
        magnet_link=link,
        category=result.Category,
        tracker=result.Tracker or "",
        Size=result.Size,
        languages=result.Languages,
        subs=result.Subs,
        year=result.Year or 0,
        seeders=result.Seeders,
    )
    await TorrentSearchResult.publish(msg)
