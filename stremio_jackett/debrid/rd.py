import asyncio
import concurrent.futures
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


async def add_link(magnet_link: str, debrid_token: str) -> str | None:
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


async def instant_availability(torrent: Torrent, debrid_token: str) -> list[InstantFile]:
    api_url = f"{ROOT_URL} /torrents/instantAvailability/{torrent.info_hash}"
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.get(api_url, headers=api_headers) as response:
            if response.status not in range(200, 300):
                print(
                    f"torrent:{torrent.info_hash}: Error getting instant availability: status:{response.status}"
                )
                return []
            res = await response.json()
            if torrent.info_hash not in res:
                print(f"torrent:{torrent.info_hash}: No cached torrent files")
                return []
            cached_files: list[InstantFile] = []
            for id, file in res[torrent.info_hash]["rd"].items():
                cached_files.append(
                    InstantFile(
                        id=id,
                        filename=file["filename"],
                        filesize=file["size"],
                    )
                )
            return []


async def get_torrent_info(
    torrent_id: str,
    debrid_token: str,
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
    torrent_info: TorrentInfo | None = await get_torrent_info(
        this does not work because the torrent_id is not the hash
        torrent_id=torrent.info_hash,
        debrid_token=debrid_token,
    )
    if not torrent_info:
        print(f"torrent:{torrent.info_hash}: No torrent info found.")
        return None

    cached_files: list[InstantFile] = await instant_availability(torrent, debrid_token)
    if len(cached_files) < 1:
        return None

    print(f"torrent:{torrent.info_hash}: RD Cached links found.")
    # pick the largest cached file
    largest_file: InstantFile = max(cached_files, key=lambda f: f.filesize)
    matched_files: list[str] = [
        link for link in torrent_info.links if link.endswith(largest_file.filename)
    ]
    if not matched_files or len(matched_files) < 1:
        print(f"torrent:{torrent.info_hash}: Could not fine matched file in torrent links")
        return None
    unrestricted_link: UnrestrictedLink | None = await unrestrict_link(
        torrent=torrent,
        link=matched_files[0],
        debrid_token=debrid_token,
    )
    if not unrestricted_link:
        print(f"torrent:{torrent.info_hash}: Could not get unrestrict link")
        return None
    return unrestricted_link

    # torrent_id = await add_link(magnet_link=torrent.url, debrid_token=debrid_token)
    # if not torrent_id:
    #     print(f"No torrent for {torrent.url}.")
    #     return None

    # print(f"torrent:{torrent.info_hash}: Magnet added to RD")
    # if season_episode:
    #     print(f"torrent:{torrent_id}: Setting episode file for season/episode...")
    #     await select_torrent_file(
    #         torrent_id=torrent_id, debrid_token=debrid_token, season_episode=season_episode
    #     )
    # else:
    #     print(f"torrent:{torrent_id}: Setting movie file...")
    #     await select_torrent_file(torrent_id=torrent_id, debrid_token=debrid_token)

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
