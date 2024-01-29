import json
import re
from typing import Any

import aiohttp
from diskcache import Cache  # type: ignore
from pydantic import BaseModel

from stremio_jackett.jackett_models import SearchResult
from stremio_jackett.torrent import Torrent

cache: Cache = Cache(__name__)


class SearchQuery(BaseModel):
    name: str
    type: str
    season: str | None = None
    episode: str | None = None


async def search(
    debrid_api_key: str,
    jackett_url: str,
    jackett_api_key: str,
    search_query: SearchQuery,
    max_results: int,
) -> list[Torrent]:
    search_url: str = f"{jackett_url}/api/v2.0/indexers/all/results"
    category: str = "2000" if search_query.type == "movie" else "5000"
    suffix: str = (
        f" S{search_query.season} E{search_query.episode}" if search_query.type == "series" else ""
    )
    params: dict[str, Any] = {
        "apikey": jackett_api_key,
        "Category": category,
        "Query": f"{search_query.name}{suffix}",
    }

    torrents: list[Torrent] = []
    async with aiohttp.ClientSession() as session:
        print(f"Searching Jackett for {search_query.name} with params {json.dumps(params)}...")
        async with session.get(
            search_url,
            params=params,
            timeout=60,
            headers={"Accept": "application/json"},
        ) as response:
            if response.status != 200:
                print(f"No results from Jackett status:{response.status}")
                return []
            response_json = await response.json()

    search_results: list[SearchResult] = [
        SearchResult(**result) for result in response_json["Results"]
    ]
    for r in search_results:
        if len(torrents) >= max_results:
            return torrents

        if r.InfoHash and r.MagnetUri:
            torrents.append(
                Torrent(
                    guid=r.Guid,
                    info_hash=r.InfoHash,
                    title=r.Title,
                    size=r.Size,
                    url=r.MagnetUri,
                    seeders=r.Seeders,
                )
            )
            continue

        elif r.Link and r.Link.startswith("http"):
            magnet_link: str = await resolve_magnet_link(guid=r.Guid, link=r.Link)
            if not magnet_link:
                print(f"Could not resolve magnet link for {r.Link}. Skipping")
                continue

            info_hash: str | None = r.InfoHash or magnet_to_info_hash(magnet_link)
            if info_hash:
                torrents.append(
                    Torrent(
                        guid=r.Guid,
                        info_hash=info_hash,
                        title=r.Title,
                        size=r.Size,
                        url=magnet_link,
                        seeders=r.Seeders,
                    )
                )

    return torrents


def magnet_to_info_hash(magnet_link: str):
    match = re.search("btih:([a-zA-Z0-9]+)", magnet_link)
    return match.group(1) if match else None


async def resolve_magnet_link(guid: str, link: str) -> str:
    """
    Jackett sometimes does not have a magnet link but a local URL that
    redirects to a magnet link. This will not work if adding to RD and
    Jackett is not publicly hosted. Most of the time we can resolve it
    locally. If not we will just pass it along to RD anyway
    """
    if link.startswith("magnet"):
        return link
    if guid in cache:
        return cache.get(guid)  # type: ignore

    print(f"Following redirect for {link}")
    async with aiohttp.ClientSession() as session:
        async with session.get(link, allow_redirects=False) as response:
            if response.status == 302:
                location = response.headers.get("Location", "")
                print(f"Updated link to {location}.")
                return location
            else:
                print(
                    f"Didn't find redirect: {response.status}. Trying anyway but this may fail if Jackett is not public."
                )
                return link
