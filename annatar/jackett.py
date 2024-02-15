import asyncio
import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional

import aiohttp
import structlog
from prometheus_client import Histogram
from structlog.contextvars import bound_contextvars

from annatar import human, instrumentation
from annatar.database import db
from annatar.debrid import magnet
from annatar.jackett_models import (
    Indexer,
    SearchQuery,
    SearchResult,
    SearchResults,
    Torrents,
)
from annatar.torrent import Torrent

log = structlog.get_logger(__name__)

MAX_RESULTS = int(os.environ.get("JACKETT_MAX_RESULTS", 10))
JACKETT_TIMEOUT = int(os.environ.get("JACKETT_TIMEOUT", 5))


REQUEST_DURATION = Histogram(
    name="jackett_request_duration_seconds",
    documentation="Duration of Jackett requests in seconds",
    labelnames=["method", "indexer", "status", "cached"],
    registry=instrumentation.REGISTRY,
)


async def get_indexers() -> list[Indexer]:
    return Indexer.all()


async def search_indexer(
    search_query: SearchQuery,
    jackett_url: str,
    jackett_api_key: str,
    indexer: str,
    imdb: int | None = None,
) -> list[Torrent]:
    suffix: str = "" if search_query.type == "series" else f"{search_query.year}"
    cache_key: str = ":".join(
        [
            f"jackett:indexer:{indexer}:search:{search_query.type}:{search_query.name}",
            suffix,
        ]
    )
    cached_torrents: Torrents | None = await db.get_model(cache_key, Torrents)
    if cached_torrents:
        return cached_torrents.items

    sanitized_name: str = re.sub(r"\W", " ", search_query.name)
    category: str = "2000" if search_query.type == "movie" else "5000"

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

    search_results: list[SearchResult] = sorted(
        raw_results,
        key=lambda r: r.Seeders,
        reverse=True,
    )

    torrents: dict[str, Torrent] = {}
    tasks = [
        asyncio.create_task(map_matched_result(result=result, search_query=search_query, imdb=imdb))
        for result in search_results
    ]

    for task in asyncio.as_completed(tasks):
        torrent: Optional[Torrent] = await task
        if torrent and human.score_name(search_query, torrent.title) > 0:
            torrents[torrent.info_hash] = torrent
            await db.set_model(
                key=f"torrent:{torrent.info_hash}", model=torrent, ttl=timedelta(weeks=8)
            )
            log.info(
                "found a torrent",
                tracker=indexer,
                info_hash=torrent.info_hash,
                title=torrent.title,
                seeders=torrent.seeders,
            )

    # prioritize items by quality
    prioritized_list: list[Torrent] = list(
        sorted(
            list(torrents.values()),
            key=lambda t: human.score_name(
                search_query,
                t.title,
            ),
            reverse=True,
        )
    )

    await db.set_model(cache_key, Torrents(items=prioritized_list), ttl=timedelta(days=7))

    return prioritized_list


async def search_indexers(
    search_query: SearchQuery,
    jackett_url: str,
    jackett_api_key: str,
    max_results: int,
    imdb: int | None = None,
    timeout: int = 60,
    indexers: list[Indexer] = Indexer.all(),
) -> list[Torrent]:
    log.info("searching indexers", indexers=indexers)
    torrents: dict[str, Torrent] = {}
    tasks = [
        asyncio.create_task(
            search_indexer(
                search_query=search_query,
                jackett_url=jackett_url,
                jackett_api_key=jackett_api_key,
                imdb=imdb,
                indexer=indexer.id,
            )
        )
        for indexer in indexers
    ]
    for task in asyncio.as_completed(tasks):
        indexer_results: list[Torrent] = await task
        for torrent in indexer_results:
            if torrent and human.score_name(search_query, torrent.title) > 0:
                torrents[torrent.info_hash] = torrent
                if len(torrents) >= max_results:
                    break

    for task in tasks:
        if not task.done():
            task.cancel()

    return list(torrents.values())


async def execute_search(
    jackett_url: str,
    jackett_api_key: str,
    indexer: str,
    params: dict[str, Any],
) -> list[SearchResult]:
    start_time = datetime.now()
    response_status: int = 200
    cached_response: bool = False
    try:
        kvs: str = ":".join([f"{k}:{v}" for k, v in params.items()])
        cache_key: str = f"jackett:indexer:{indexer}:search:{kvs}"
        cached_results: SearchResults | None = await db.get_model(cache_key, SearchResults)
        if cached_results:
            cached_response = True
            return cached_results.Results

        url: str = f"{jackett_url}/api/v2.0/indexers/all/results"
        with bound_contextvars(
            search_params=params,
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
                            )
                            return []
                        response_json = await response.json()
                except TimeoutError as err:
                    log.error("jacket search timeout", error=err, timeout=JACKETT_TIMEOUT)
                    return []
                except Exception as err:
                    log.error("jacket search error", error=err)
                    return []

        res: SearchResults = SearchResults(
            Results=[SearchResult(**result) for result in response_json["Results"]]
        )
        if res.Results:
            await db.set_model(cache_key, res, timedelta(days=1))
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
) -> Torrent | None:
    if imdb and result.Imdb and result.Imdb != imdb:
        log.info(
            "skipping mismatched IMDB",
            wanted=imdb,
            got=result.Imdb,
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

    if result.InfoHash and result.MagnetUri:
        return Torrent(
            guid=result.Guid,
            info_hash=result.InfoHash,
            title=result.Title,
            size=result.Size,
            url=result.MagnetUri,
            seeders=result.Seeders,
            tracker=result.Tracker,
            imdb=result.Imdb,
        )

    if result.Link and result.Link.startswith("http"):
        magnet_link: str | None = await resolve_magnet_link(guid=result.Guid, link=result.Link)
        if not magnet_link:
            return None

        info_hash: str | None = result.InfoHash or magnet.get_info_hash(magnet_link)
        if not info_hash:
            log.info("Could not find info hash in magnet link", magnet=magnet_link)
            return None

        torrent: Torrent = Torrent(
            guid=result.Guid,
            info_hash=info_hash,
            title=result.Title,
            size=result.Size,
            url=magnet_link,
            seeders=result.Seeders,
            tracker=result.Tracker,
        )
        log.info(
            "found torrent", torrent=torrent.title, seeders=torrent.seeders, tracker=torrent.tracker
        )
        return torrent

    return None


async def resolve_magnet_link(guid: str, link: str) -> str | None:
    """
    Jackett sometimes does not have a magnet link but a local URL that
    redirects to a magnet link. This will not work if adding to RD and
    Jackett is not publicly hosted. Most of the time we can resolve it
    locally. If not we will just pass it along to RD anyway
    """
    if link.startswith("magnet"):
        return link

    start_time = datetime.now()
    response_status: int = 200
    cached_response: bool = False
    try:
        cache_key: str = f"jackett:magnet:{guid}:url"
        cached_magnet: Optional[str] = await db.get(cache_key)
        if cached_magnet:
            cached_response = True
            return cached_magnet

        log.info("magnet resolve: following redirect", guid=guid, link=link)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                link, allow_redirects=False, timeout=JACKETT_TIMEOUT
            ) as response:
                response_status = response.status
                if response.status == 302:
                    location = response.headers.get("Location", "")
                    log.info("magnet resolve: found redirect", guid=guid, magnet=location)
                    return location
                else:
                    log.info("magnet resolve: no redirect found", guid=guid, status=response.status)
                    return None
        await db.set(cache_key, location)
    except TimeoutError as err:
        log.error("magnet resolve: timeout", guid=guid, error=err)
        return None
    except Exception as err:
        log.error("magnet resolve error", error=err)
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
