import asyncio
import concurrent.futures
import json
from os import getenv
from typing import Optional

import aiohttp
from pydantic import BaseModel

from stremio_jackett.debrid.rd_models import (
    InstantFile,
    StreamableFile,
    TorrentFile,
    TorrentInfo,
    UnrestrictedLink,
)
from stremio_jackett.torrent import Torrent

ROOT_URL = "https://api.real-debrid.com/rest/1.0"


async def select_biggest_file(
    files: list[TorrentFile],
    season_episode: str | None,
) -> int:
    if len(files) == 0:
        print("No files, returning 0")
        return 0
    if len(files) == 1:
        print(f"Only one file, returning {files[0].id}")
        return files[0].id

    sorted_files: list[TorrentFile] = sorted(files, key=lambda f: f.bytes, reverse=True)
    if not season_episode:
        print(f"No season_episode, returning {sorted_files[0].id}")
        return sorted_files[0].id

    s_e = f"S{season_episode.replace(':', 'E')}".lower()
    for file in sorted_files:
        print(f"Searching for {s_e} in {file}")
        path = file.path.lower()
        if s_e in path:
            return file.id
        if s_e.replace("0", "") in path:
            return file.id
    print(f"No file found for {s_e}, returning {sorted_files[0].id}")
    return 0


async def add_link(magnet_link: str, debrid_token: str) -> str | None:
    api_url = f"{ROOT_URL}/torrents/addMagnet"
    body = {"magnet": magnet_link}

    print(api_url)
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.post(api_url, headers=api_headers, data=body) as response:
            print(f"Got status adding magnet to RD: status={response.status}, magnet={magnet_link}")
            if response.status not in range(200, 300):
                return None
            response_json = await response.json()
            print(f"Magnet added to RD: Torrent:{magnet_link}")
            return response_json["id"]


async def get_instant_availability(info_hash: str, debrid_token: str) -> list[InstantFile]:
    api_url = f"{ROOT_URL}/torrents/instantAvailability/{info_hash}"
    print(api_url)
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.get(api_url, headers=api_headers) as response:
            if response.status not in range(200, 300):
                print(
                    f"torrent:{info_hash}: Error getting instant availability: status:{response.status}"
                )
                response.raise_for_status()
                return []
            res = await response.json()

    cached_files: list[InstantFile] = [
        InstantFile(id=int(id_key), **file_info)
        for value in res.values()
        for item in value.get("rd", [])
        for id_key, file_info in item.items()
    ]
    print(f"Found {len(cached_files)} cached files.")
    return cached_files


async def get_torrent_link(info_hash: str, debrid_token: str) -> str | None:
    api_url = f"{ROOT_URL}/torrents"
    print(api_url)
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.get(api_url, headers=api_headers) as response:
            if response.status not in range(200, 300):
                print(f"Error getting torrent list: {response.status}")
                return None
            response_json = await response.json()
    # parse list of TorrentInfo from response.json()
    print(f"torrent:{info_hash}: Got torrent list: {json.dumps(response_json, indent=2)}")
    for torrent in response_json:
        if torrent["hash"].lower() != info_hash.lower():
            continue
        links = torrent["links"]
        if links:
            link = links[0]
            print(f"torrent:{info_hash}: Torrent link found: {link}")
            return link
        else:
            print(f"torrent:{info_hash}: Torrent has no links?")
            return None
    print(f"torrent:{info_hash}: Torrent not found in list.")
    return None


async def get_torrent_info(
    torrent_id: str,
    debrid_token: str,
) -> TorrentInfo | None:
    api_url = f"{ROOT_URL}/torrents/info/{torrent_id}"
    print(api_url)
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.get(api_url, headers=api_headers) as response:
            if response.status not in range(200, 300):
                print(f"Error getting torrent info: {response.status}")
                return None
            response_json = await response.json()
            torrent_info: TorrentInfo = TorrentInfo(**response_json)
            return torrent_info


async def select_torrent_file(
    torrent_id: str,
    debrid_token: str,
    season_episode: Optional[str] = None,
):
    torrent_info: TorrentInfo | None = await get_torrent_info(
        torrent_id=torrent_id,
        debrid_token=debrid_token,
    )

    if not torrent_info:
        print("torrent:{torrent_id}. No torrent info found.")
        return

    torrent_files: list[TorrentFile] = torrent_info.files
    torrent_file_id = await select_biggest_file(files=torrent_files, season_episode=season_episode)
    print(f"torrent:{torrent_id}: Selected file: {torrent_file_id}")
    api_url = f"{ROOT_URL}/torrents/selectFiles/{torrent_id}"
    body = {"files": torrent_file_id}

    print(api_url)
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        await session.post(api_url, headers=api_headers, data=body)


async def unrestrict_link(
    torrent: Torrent,
    link: str,
    debrid_token: str,
) -> UnrestrictedLink | None:
    api_url = f"{ROOT_URL}/unrestrict/link"
    body = {"link": link}

    print(api_url)
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.post(api_url, headers=api_headers, data=body) as response:
            if response.status not in range(200, 300):
                print(
                    f"torrent:{torrent.info_hash}: Error getting unrestrict/link: {response.status}"
                )
                return None
            unrestrict_response_json = await response.json()
            unrestrict_response_json["torrent"] = torrent
            unrestrict_info: UnrestrictedLink = UnrestrictedLink(**unrestrict_response_json)
            print(f"torrent:{torrent.info_hash}: RD link: {unrestrict_info.download}")
            return unrestrict_info


async def get_stream_link(
    torrent: Torrent,
    season_episode: str,
    debrid_token: str,
) -> UnrestrictedLink | None:
    cached_files: list[InstantFile] = await get_instant_availability(
        torrent.info_hash, debrid_token
    )
    if not cached_files:
        return None
    print(f"torrent:{torrent.info_hash}: {len(cached_files)} cached files found.")

    torrent_id = await add_link(magnet_link=torrent.url, debrid_token=debrid_token)
    if not torrent_id:
        print(f"torrent:{torrent.info_hash}: No torrent for {torrent.url}.")
        return None

    print(f"torrent:{torrent.info_hash}: Magnet added to RD")

    print(
        f"torrent:{torrent_id}: Setting selecting {season_episode if season_episode else 'movie'} file."
    )
    await select_torrent_file(
        torrent_id=torrent_id, debrid_token=debrid_token, season_episode=season_episode
    )

    torrent_link: str | None = await get_torrent_link(
        info_hash=torrent.info_hash,
        debrid_token=debrid_token,
    )
    if not torrent_link:
        print(f"torrent:{torrent.info_hash}: No torrent links found.")
        return None

    print(f"torrent:{torrent.info_hash}: RD Cached links found.")

    unrestricted_link: UnrestrictedLink | None = await unrestrict_link(
        torrent=torrent,
        link=torrent_link,
        debrid_token=debrid_token,
    )
    if not unrestricted_link:
        print(f"torrent:{torrent.info_hash}: Could not get unrestrict link")
        return None
    return unrestricted_link

    # torrent_info: TorrentInfo | None = await get_torrent_info(
    #     torrent_id=torrent_id, season_episode=season_episode, debrid_token=debrid_token
    # )

    # if not torrent_info:
    #     print(f"torrent:{torrent_id}: No torrent info found.")
    #     return None

    # if len(torrent_info.links) >= 1:
    #     print(f"torrent:{torrent_id}: RD link found.")
    # else:
    #     print(f"torrent:{torrent_id}: No RD link found. Torrent is not cached. Skipping")
    #     await delete_torrent(torrent_id=torrent_id, debrid_token=debrid_token)
    #     return None

    # download_link = torrent_info.links[0]
    # return await unrestrict_link(torrent, download_link, debrid_token)


async def delete_torrent(torrent_id: str, debrid_token: str):
    async with aiohttp.ClientSession() as session:
        api_url = f"{ROOT_URL}/torrents/delete/{torrent_id}"
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.delete(api_url, headers=api_headers) as response:
            print(f"torrent:{torrent_id} cleaned up torrent")


async def get_stream_links(
    torrents: list[Torrent],
    debrid_token: str,
    season_episode: str,
    max_results: int = 5,
) -> list[UnrestrictedLink]:
    """
    Generates a list of RD links for each torrent link.
    """

    def __run(torrent: Torrent) -> Optional[UnrestrictedLink]:
        return asyncio.run(
            get_stream_link(
                torrent=torrent,
                season_episode=season_episode,
                debrid_token=debrid_token,
            )
        )

    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(executor.map(__run, torrents))

    return [r for r in results if r]
