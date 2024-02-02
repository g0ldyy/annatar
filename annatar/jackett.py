import asyncio
from functools import lru_cache
from typing import Any, Optional

import aiohttp
import structlog

from annatar import human
from annatar.debrid import magnet
from annatar.jackett_models import Indexer, SearchQuery, SearchResult
from annatar.logging import timestamped
from annatar.torrent import Torrent

log = structlog.get_logger(__name__)


async def get_indexers() -> list[Indexer]:
    return Indexer.all()


@timestamped(["indexer", "imdb"])
async def search_indexer(
    search_query: SearchQuery,
    jackett_url: str,
    jackett_api_key: str,
    max_results: int,
    indexer: str,
    imdb: int | None = None,
    timeout: int = 60,
) -> list[Torrent]:
    search_url: str = f"{jackett_url}/api/v2.0/indexers/all/results"
    category: str = "2000" if search_query.type == "movie" else "5000"
    suffix: str = (
        f"S{str(search_query.season).zfill(2)} E{str(search_query.episode).zfill(2)}"
        if search_query.type == "series"
        else search_query.year or ""
    )
    params: dict[str, Any] = {
        "apikey": jackett_api_key,
        "Category": category,
        "Query": f"{search_query.name} {suffix}".strip(),
    }
    params["Tracker[]"] = indexer

    async with aiohttp.ClientSession() as session:
        log.info(
            "searching jackett",
            query=search_query.model_dump(),
            params=params,
            indexer=indexer,
        )
        try:
            async with session.get(
                search_url,
                params=params,
                timeout=timeout,
                headers={"Accept": "application/json"},
            ) as response:
                if response.status != 200:
                    log.info(
                        "jacket search failed",
                        status=response.status,
                        reason=response.reason,
                        body=await response.text(),
                        indexer=indexer,
                    )
                    return []
                response_json = await response.json()
        except TimeoutError as err:
            log.error(
                "jacket search timeout",
                error=err,
                query=search_query.model_dump(),
                params=params,
                url=search_url,
                indexer=indexer,
            )
            return []

    search_results: list[SearchResult] = sorted(
        [SearchResult(**result) for result in response_json["Results"]],
        key=lambda r: r.Seeders,
        reverse=True,
    )

    torrents: dict[str, Torrent] = {}
    tasks = [
        asyncio.create_task(map_matched_result(result=result, imdb=imdb))
        for result in search_results
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
            if len(torrents) >= max_results:
                break

    for task in tasks:
        if not task.done():
            task.cancel()

    # prioritize items by quality
    prioritized_list: list[Torrent] = sorted(
        list(torrents.values()),
        key=lambda t: human.sort_priority(search_query.name, t.title),
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
                max_results=max_results,
                jackett_url=jackett_url,
                jackett_api_key=jackett_api_key,
                imdb=imdb,
                timeout=timeout / 5,
                indexer=indexer.id,
            )
        )
        for indexer in indexers
    ]
    for task in asyncio.as_completed(tasks):
        indexer_results: list[Optional[Torrent]] = await task
        for torrent in indexer_results:
            if torrent:
                torrents[torrent.info_hash] = torrent
                if len(torrents) >= max_results:
                    break

    for task in tasks:
        if not task.done():
            task.cancel()

    return list(torrents.values())


async def map_matched_result(result: SearchResult, imdb: int | None) -> Torrent | None:
    if imdb and result.Imdb and result.Imdb != imdb:
        log.info(
            "skipping mismatched IMDB",
            wanted=imdb,
            got=result.Imdb,
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


@lru_cache(maxsize=1024, typed=True)
async def resolve_magnet_link(guid: str, link: str) -> str | None:
    """
    Jackett sometimes does not have a magnet link but a local URL that
    redirects to a magnet link. This will not work if adding to RD and
    Jackett is not publicly hosted. Most of the time we can resolve it
    locally. If not we will just pass it along to RD anyway
    """
    if link.startswith("magnet"):
        return link

    log.info("magnet resolve: following redirect", guid=guid, link=link)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(link, allow_redirects=False, timeout=1) as response:
                if response.status == 302:
                    location = response.headers.get("Location", "")
                    log.info("magnet resolve: found redirect", guid=guid, magnet=location)
                    return location
                else:
                    log.info("magnet resolve: no redirect found", guid=guid, status=response.status)
                    return None
    except TimeoutError as err:
        log.error("magnet resolve: timeout", guid=guid, error=err)
        return None
