import asyncio
import json
import xml.etree.ElementTree as ET
from typing import Any

import aiohttp
from pydantic import BaseModel


class JackettResult(BaseModel):
    size: int
    title: str
    url: str
    seeders: int


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
) -> list[JackettResult]:
    search_url: str = f"{jackett_url}/api/v2.0/indexers/all/results/torznab/api"
    category: str = "2000" if search_query.type == "movie" else "5000"
    suffix: str = (
        f" S{search_query.season}E{search_query.episode}" if search_query.type == "series" else ""
    )
    params: dict[str, Any] = {
        "apikey": jackett_api_key,
        "cat": category,
        "q": f"{search_query.name}{suffix}",
    }

    async with aiohttp.ClientSession() as session:
        print(f"Searching Jackett for {search_query.name} with params {json.dumps(params)}...")
        async with session.get(search_url, params=params) as response:
            response_body_raw = await response.read()
            if response.status == 200 and response_body_raw:
                return await parse_xml(response_body_raw.decode("utf-8"), limit=max_results)
            else:
                print(f"No results from Jackett status:{response.status}")
                return []
    return []


async def parse_xml(xml: str, limit: int) -> list[JackettResult]:
    # print(f"Parsing XML: \n{xml}")
    root = ET.fromstring(xml)
    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else []

    results: list[JackettResult] = await asyncio.gather(
        *[parse_xml_result(item) for item in items[:limit]]
    )
    return sorted(results, key=lambda x: (x.seeders or 0), reverse=True)


async def parse_xml_result(item: Any) -> JackettResult:
    torznab_attr = item.find("torznab:attr")
    seeders = 0
    if torznab_attr is not None:
        seeders_attr = torznab_attr.find("./[@name='seeders']")
        if seeders_attr is not None:
            seeders = int(seeders_attr.get("value", "0"))

    url: str = item.findtext("link", "")
    if not url.startswith("magnet"):
        url = await resolve_magnet_link(url)
    return JackettResult(
        title=item.findtext("title", ""),
        size=int(item.findtext("size", "0")),
        url=url,
        seeders=seeders,
    )


async def resolve_magnet_link(link: str) -> str:
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
