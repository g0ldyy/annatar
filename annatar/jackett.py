import asyncio
import json
import os
from datetime import timedelta
from typing import Any, Optional

import aiohttp
import structlog
from structlog.contextvars import bound_contextvars

from annatar import human
from annatar.database import db
from annatar.debrid import magnet
from annatar.jackett_models import Indexer, SearchQuery, SearchResult
from annatar.logging import timestamped
from annatar.torrent import Torrent

log = structlog.get_logger(__name__)

MAX_RESULTS = int(os.environ.get("JACKETT_MAX_RESULTS", 10))
JACKETT_TIMEOUT = int(os.environ.get("JACKETT_TIMEOUT", 5))


async def get_indexers() -> list[Indexer]:
    return Indexer.all()


@timestamped()
async def cache_torrents(torrents: list[Torrent]) -> None:
    tasks = [
        asyncio.create_task(
            db.set(
                f"torrent:{torrent.info_hash}",
                torrent.model_dump_json(),
                ttl=timedelta(weeks=52),
            )
        )
        for torrent in torrents
    ]
    await asyncio.gather(*tasks)


@timestamped(["indexer", "imdb"])
async def search_indexer(
    search_query: SearchQuery,
    jackett_url: str,
    jackett_api_key: str,
    indexer: str,
    imdb: Optional[int] = None,
) -> list[Torrent]:
    cache_key: str = f"jackett:search:{indexer}:{search_query.name}:{search_query.year}"
    if search_query.type == "series":
        cache_key += f":{search_query.season}:{search_query.episode}"

    cached_results: Optional[str] = await db.get(cache_key)
    if cached_results:
        return [Torrent.model_validate(t) for t in json.loads(cached_results)]

    with bound_contextvars(
        indexer=indexer,
        query=search_query,
    ):
        res: list[Torrent] = await _search_indexer(
            search_query=search_query,
            jackett_url=jackett_url,
            jackett_api_key=jackett_api_key,
            indexer=indexer,
            imdb=imdb,
        )
        await db.set(
            cache_key,
            json.dumps([r.model_dump() for r in res]),
            ttl=timedelta(hours=1),
        )
    await cache_torrents(res)

    return res


async def _search_indexer(
    search_query: SearchQuery,
    jackett_url: str,
    jackett_api_key: str,
    indexer: str,
    imdb: int | None = None,
) -> list[Torrent]:
    category: str = "2000" if search_query.type == "movie" else "5000"
    suffixes: list[str] = [str(search_query.year)]
    if search_query.type == "series":
        suffixes = [
            f"S{str(search_query.season).zfill(2)}",
            f"S{str(search_query.season).zfill(2)} E{str(search_query.episode).zfill(2)}",
        ]

    tasks = [
        execute_search(
            jackett_api_key=jackett_api_key,
            jackett_url=jackett_url,
            indexer=indexer,
            params={
                "Category": category,
                "Query": f"{search_query.name} {suffix}".strip(),
                "Tracker[]": indexer,
            },
        )
        for suffix in suffixes
    ]
    search_results: list[SearchResult] = sorted(
        [item for sublist in await asyncio.gather(*tasks) for item in sublist],
        key=lambda r: r.Seeders,
        reverse=True,
    )

    torrents: dict[str, Torrent] = {}
    tasks = [
        asyncio.create_task(map_matched_result(result=result, search_query=search_query, imdb=imdb))
        for result in search_results[: MAX_RESULTS * 2]
    ]

    for task in asyncio.as_completed(tasks):
        torrent: Optional[Torrent] = await task
        if torrent:
            torrents[torrent.info_hash] = torrent
            log.info(
                "found a torrent",
                tracker=indexer,
                info_hash=torrent.info_hash,
                title=torrent.title,
                seeders=torrent.seeders,
            )
            if len(torrents) >= MAX_RESULTS:
                break

    for task in tasks:
        if not task.done():
            task.cancel()

    # prioritize items by quality
    prioritized_list: list[Torrent] = list(
        reversed(
            sorted(
                list(torrents.values()),
                key=lambda t: human.score_name(
                    search_query.name,
                    search_query.year,
                    t.title,
                ),
            )
        )
    )

    return prioritized_list


@timestamped(["imdb", "jackett_url", "search_query", "max_results", "indexers"])
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
            if torrent:
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

    return [SearchResult(**result) for result in response_json["Results"]]


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


@timestamped(["guid", "link"])
async def resolve_magnet_link(guid: str, link: str) -> str | None:
    """
    Jackett sometimes does not have a magnet link but a local URL that
    redirects to a magnet link. This will not work if adding to RD and
    Jackett is not publicly hosted. Most of the time we can resolve it
    locally. If not we will just pass it along to RD anyway
    """
    if link.startswith("magnet"):
        return link

    cache_key: str = f"jackett:magnet:{guid}:url"
    cached_magnet: Optional[str] = await db.get(cache_key)
    if cached_magnet:
        log.debug("magnet resolved", guid=guid)
        return cached_magnet

    log.info("magnet resolve: following redirect", guid=guid, link=link)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                link, allow_redirects=False, timeout=JACKETT_TIMEOUT
            ) as response:
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
