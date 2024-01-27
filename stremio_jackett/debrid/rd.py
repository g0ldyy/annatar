import concurrent.futures
from os import getenv
from typing import Optional

from pydantic import BaseModel

root_url = "https://api.real-debrid.com/rest/1.0"

import asyncio

import aiohttp


class TorrentFile(BaseModel):
    id: str
    path: str
    bytes: int = 0


class File(BaseModel):
    id: int
    path: str
    bytes: int
    selected: int


class TorrentInfo(BaseModel):
    id: str
    filename: str
    original_filename: str
    hash: str
    bytes: int
    original_bytes: int
    host: str
    split: int
    progress: int
    status: str
    added: str
    files: list[File]
    links: list[str]
    ended: Optional[str] = None
    speed: Optional[int] = None
    seeders: Optional[int] = None


class UnrestrictedLink(BaseModel):
    id: str
    filename: str
    mimeType: str  # Mime Type of the file, guessed by the file extension
    filesize: int  # Filesize in bytes, 0 if unknown
    link: str  # Original link
    host: str  # Host main domain
    chunks: int  # Max Chunks allowed
    crc: int  # Disable / enable CRC check
    download: str  # Generated link
    streamable: int  # Is the file streamable on website


async def select_biggest_file_season(files: list[TorrentFile], season_episode: str) -> int:
    return int(next((file.id for file in files if season_episode and season_episode in file.path)))


async def add_magnet_to_rd(magnet_link: str, debrid_token: str):
    api_url = "{root_url}/torrents/addMagnet"
    body = {"magnet": magnet_link}

    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.post(api_url, headers=api_headers, data=body) as response:
            response_json = await response.json()
            return response_json["id"]


async def get_torrent_info(
    torrent_id: str, debrid_token: str, season_episode: Optional[str] = None
) -> TorrentInfo:
    api_url = f"{root_url}/torrents/info/{torrent_id}"

    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.get(api_url, headers=api_headers) as response:
            response_json = await response.json()
            torrent_info: TorrentInfo = TorrentInfo(**response_json)
            return torrent_info


async def set_file_rd(torrent_id: str, debrid_token: str, season_episode: Optional[str] = None):
    torrent_info: TorrentInfo = await get_torrent_info(
        torrent_id=torrent_id, debrid_token=debrid_token, season_episode=season_episode
    )

    torrent_files: list[TorrentFile] = torrent_info.files
    max_index = (
        await select_biggest_file_season(files=torrent_files, season_episode=season_episode)
        if season_episode
        else max(range(len(torrent_files)), key=lambda i: torrent_files[i].bytes)
    )

    torrent_file_id = (
        torrent_files[max_index].id if season_episode else torrent_files[max_index - 1].id
    )
    api_url = f"{root_url}/torrents/selectFiles/{torrent_id}"
    body = {"files": torrent_file_id}

    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        await session.post(api_url, headers=api_headers, data=body)


async def get_movie_rd_link(
    torrent_link: str, season_episode: str, debrid_token: str
) -> UnrestrictedLink | None:
    torrent_id = await add_magnet_to_rd(magnet_link=torrent_link, debrid_token=debrid_token)
    print(f"Magnet added to RD. ID: {torrent_id}")

    if season_episode:
        print("Setting episode file for season/episode...")
        await set_file_rd(
            torrent_id=torrent_id, debrid_token=debrid_token, season_episode=season_episode
        )
    else:
        print("Setting movie file...")
        await set_file_rd(torrent_id=torrent_id, debrid_token=debrid_token)

    print("Waiting for RD link...")
    torrent_info: TorrentInfo = await get_torrent_info(
        torrent_id=torrent_id, season_episode=season_episode, debrid_token=debrid_token
    )

    if len(torrent_info.links) >= 1:
        print("RD link found.")
    else:
        print("No RD link found.")
        return None

    download_link = torrent_info.links[0]
    api_url = "{root_url}/unrestrict/link"
    body = {"link": download_link}

    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.post(api_url, headers=api_headers, data=body) as response:
            unrestrict_response_json = await response.json()

    unrestrict_info: UnrestrictedLink = UnrestrictedLink(**unrestrict_response_json)
    print(f"RD link: {unrestrict_info.download}")
    return unrestrict_info


async def get_movie_rd_links(
    torrent_links: list[str],
    debrid_token: str,
    season_episode: str,
) -> dict[str, Optional[UnrestrictedLink]]:
    """
    Generates a list of RD links for each torrent link.
    """

    def __run(torrent_link) -> Optional[UnrestrictedLink]:
        return asyncio.run(
            get_movie_rd_link(
                torrent_link=torrent_link, season_episode=season_episode, debrid_token=debrid_token
            )
        )

    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(executor.map(__run, torrent_links))

    return {torrent_links[i]: result for i, result in enumerate(results) if result is not None}
