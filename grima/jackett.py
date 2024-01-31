import asyncio
import concurrent.futures
import json
import re
from concurrent.futures import as_completed
from functools import lru_cache
from typing import Any, Optional

import aiohttp

from grima.debrid import magnet
from grima.jackett_models import SearchQuery, SearchResult
from grima.torrent import Torrent

PRIORITY_WORDS: list[str] = [r"\b(4K|2160p)\b", r"\b1080p\b", r"\b720p\b"]


async def search(
    debrid_api_key: str,
    jackett_url: str,
    jackett_api_key: str,
    search_query: SearchQuery,
    max_results: int,
    imdb: int | None = None,
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

    async with aiohttp.ClientSession() as session:
        print(
            f"Searching Jackett for {search_query.model_dump()} with params {json.dumps(params)}..."
        )
        async with session.get(
            search_url,
            params=params,
            timeout=10,
            headers={"Accept": "application/json"},
        ) as response:
            if response.status != 200:
                print(f"No results from Jackett status:{response.status}")
                return []
            response_json = await response.json()

    search_results: list[SearchResult] = sorted(
        [SearchResult(**result) for result in response_json["Results"]],
        key=lambda r: r.Seeders,
        reverse=True,
    )

    # sync map search results to torrents async
    def __run(result: SearchResult) -> Optional[Torrent]:
        return asyncio.run(map_matched_result(result=result, imdb=imdb))

    torrents: dict[str, Torrent] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(__run, result) for result in search_results]

        for future in as_completed(futures):
            torrent: Torrent | None = future.result()
            if torrent:
                torrents[torrent.info_hash] = torrent
                if len(torrents.keys()) >= max_results:
                    break
        # cancel the remaining futures
        for future in futures:
            future.cancel()

    # prioritize items by quality
    prioritized_list: list[Torrent] = sorted(
        list(torrents.values()),
        key=lambda t: sort_priority(search_query.name, t),
    )

    return prioritized_list


async def map_matched_result(result: SearchResult, imdb: int | None) -> Torrent | None:
    if imdb and result.Imdb and result.Imdb != imdb:
        print(f"Skipping mismatched IMDB {result.Imdb} for {result.Title}. Expected {imdb}")
        return None

    if result.InfoHash and result.MagnetUri:
        return Torrent(
            guid=result.Guid,
            info_hash=result.InfoHash,
            title=result.Title,
            size=result.Size,
            url=result.MagnetUri,
            seeders=result.Seeders,
        )

    if result.Link and result.Link.startswith("http"):
        magnet_link: str | None = await resolve_magnet_link(guid=result.Guid, link=result.Link)
        if not magnet_link:
            print(f"Could not resolve magnet link for {result.Link}. Skipping")
            return None

        info_hash: str | None = result.InfoHash or magnet.get_info_hash(magnet_link)
        if not info_hash:
            print(f"Could not find info hash for {magnet_link}. Skipping")
            return None

        return Torrent(
            guid=result.Guid,
            info_hash=info_hash,
            title=result.Title,
            size=result.Size,
            url=magnet_link,
            seeders=result.Seeders,
        )

    return None


# sort items by quality
def sort_priority(search_query: str, item: Torrent) -> int:
    name_pattern: str = re.sub(r"\W+", r"\\W+", search_query)
    print(f"search_query:{search_query} name_pattern:{name_pattern}")

    priority: int = 50
    reason: str = "no priority matches"
    for index, quality in enumerate(PRIORITY_WORDS):
        if re.search(quality, item.title, re.IGNORECASE):
            if re.search(name_pattern, item.title, re.IGNORECASE):
                priority = index
                reason = f"matched {quality} and name"
            else:
                priority = index + 10
                reason = f"matched {quality}, mismatch name"
    print(f"torrent:{item.title} priority: {priority}. reason:{reason}")
    return priority


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

    print(f"Following redirect for {link}")
    async with aiohttp.ClientSession() as session:
        async with session.get(link, allow_redirects=False, timeout=5) as response:
            if response.status == 302:
                location = response.headers.get("Location", "")
                print(f"Updated link to {location}.")
                return location
            else:
                print(f"Didn't find redirect: {response.status}. No magnet link could be found.")
                return None
