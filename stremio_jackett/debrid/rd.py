import asyncio
import concurrent.futures
from os import getenv
from typing import Optional

import aiohttp
from pydantic import BaseModel

from stremio_jackett.debrid.rd_models import TorrentFile, TorrentInfo, UnrestrictedLink

ROOT_URL = "https://api.real-debrid.com/rest/1.0"


async def select_biggest_file(files: list[TorrentFile], season_episode: str | None) -> int:
    if len(files) == 0:
        return 0
    if len(files) == 1:
        return files[0].id

    sorted_files: list[TorrentFile] = sorted(files, key=lambda f: f.bytes, reverse=True)
    if not season_episode:
        return sorted_files[0].id

    for file in sorted_files:
        if season_episode in file.path:
            return file.id
    return 0


async def add_link(link: str, debrid_token: str) -> str | None:
    magnet_link: str = link
    if link.startswith("http"):
        # Jackett sometimes does not have a magnet link but a local URL that
        # redirects to a magnet link. This will not work if adding to RD and
        # Jackett is not publicly hosted. Most of the time we can resolve it
        # locally. If not we will just pass it along to RD anyway
        print(f"Following redirect for {link}")
        async with aiohttp.ClientSession() as session:
            async with session.get(link, allow_redirects=False) as response:
                if response.status == 302:
                    magnet_link = response.headers.get("Location", default=link)
                else:
                    print(
                        f"Didn't find redirect: {response.status}. Trying anyway but this may fail if Jackett is not public."
                    )

    api_url = f"{ROOT_URL}/torrents/addMagnet"
    body = {"magnet": magnet_link}

    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.post(api_url, headers=api_headers, data=body) as response:
            print(f"Got status adding magnet to RD: status={response.status}, magnet={magnet_link}")
            if response.status not in range(200, 300):
                return None
            response_json = await response.json()
            print(f"Magnet added to RD: Torrent:{magnet_link}")
            return response_json["id"]


async def get_torrent_info(
    torrent_id: str, debrid_token: str, season_episode: Optional[str] = None
) -> TorrentInfo | None:
    api_url = f"{ROOT_URL}/torrents/info/{torrent_id}"

    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.get(api_url, headers=api_headers) as response:
            if response.status not in range(200, 300):
                print(f"Error getting torrent info: {response.status}")
                return None
            response_json = await response.json()
            torrent_info: TorrentInfo = TorrentInfo(**response_json)
            return torrent_info


async def set_file_rd(torrent_id: str, debrid_token: str, season_episode: Optional[str] = None):
    torrent_info: TorrentInfo | None = await get_torrent_info(
        torrent_id=torrent_id, debrid_token=debrid_token, season_episode=season_episode
    )

    if not torrent_info:
        print("No torrent info found.")
        return

    torrent_files: list[TorrentFile] = torrent_info.files
    torrent_file_id = await select_biggest_file(files=torrent_files, season_episode=season_episode)
    api_url = f"{ROOT_URL}/torrents/selectFiles/{torrent_id}"
    body = {"files": torrent_file_id}

    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        await session.post(api_url, headers=api_headers, data=body)


async def get_stream_link(
    torrent_link: str, season_episode: str, debrid_token: str
) -> UnrestrictedLink | None:
    torrent_id = await add_link(link=torrent_link, debrid_token=debrid_token)
    if not torrent_id:
        print("No torrent found on RD.")
        return None

    print(f"torrent:{torrent_id}: Magnet added to RD")
    if season_episode:
        print(f"torrent:{torrent_id}: Setting episode file for season/episode...")
        await set_file_rd(
            torrent_id=torrent_id, debrid_token=debrid_token, season_episode=season_episode
        )
    else:
        print(f"torrent:{torrent_id}: Setting movie file...")
        await set_file_rd(torrent_id=torrent_id, debrid_token=debrid_token)

    torrent_info: TorrentInfo | None = await get_torrent_info(
        torrent_id=torrent_id, season_episode=season_episode, debrid_token=debrid_token
    )

    if not torrent_info:
        print(f"torrent:{torrent_id}: No torrent info found.")
        return None

    if len(torrent_info.links) >= 1:
        print(f"torrent:{torrent_id}: RD link found.")
    else:
        print(f"torrent:{torrent_id}: No RD link found. Torrent is not cached. Skipping")
        return None

    download_link = torrent_info.links[0]
    api_url = f"{ROOT_URL}/unrestrict/link"
    body = {"link": download_link}

    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.post(api_url, headers=api_headers, data=body) as response:
            if response.status not in range(200, 300):
                print(f"torrent:{torrent_id}: Error getting unrestrict/link: {response.status}")
                return None
            unrestrict_response_json = await response.json()

    unrestrict_info: UnrestrictedLink = UnrestrictedLink(**unrestrict_response_json)
    print(f"torrent:{torrent_id}: RD link: {unrestrict_info.download}")
    return unrestrict_info


async def get_stream_links(
    torrent_links: list[str],
    debrid_token: str,
    season_episode: str,
    max_results: int = 5,
) -> dict[str, Optional[UnrestrictedLink]]:
    """
    Generates a list of RD links for each torrent link.
    """

    def __run(torrent_link) -> Optional[UnrestrictedLink]:
        return asyncio.run(
            get_stream_link(
                torrent_link=torrent_link, season_episode=season_episode, debrid_token=debrid_token
            )
        )

    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(executor.map(__run, torrent_links))

    return {torrent_links[i]: result for i, result in enumerate(results) if result is not None}
