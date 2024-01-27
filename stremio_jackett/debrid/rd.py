import concurrent.futures
from os import getenv
from typing import Optional

from pydantic import BaseModel

root_url = "https://api.real-debrid.com/rest/1.0"

debrid_token = getenv("REAL_DEBRID_TOKEN")
headers = {"Authorization": f"Bearer {debrid_token}"}

import asyncio

import aiohttp


async def select_biggest_file_season(files, season_episode: str):
    return next(
        (file["id"] for file in files if season_episode and season_episode in file["path"]), None
    )


async def add_magnet_to_rd(magnet_link):
    api_url = "{root_url}/torrents/addMagnet"
    body = {"magnet": magnet_link}

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, headers=headers, data=body) as response:
            response_json = await response.json()
            return response_json["id"]


async def set_file_rd(torrent_id: str, season_episode: Optional[str] = None):
    api_url = f"{root_url}/torrents/info/{torrent_id}"

    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, headers=headers) as response:
            response_json = await response.json()

    torrent_files = response_json["files"]
    max_index = (
        await select_biggest_file_season(torrent_files, season_episode)
        if season_episode
        else max(range(len(torrent_files)), key=lambda i: torrent_files[i].get("bytes", 0))
    )

    torrent_file_id = (
        torrent_files[max_index]["id"] if season_episode else torrent_files[max_index - 1]["id"]
    )
    api_url = f"{root_url}/torrents/selectFiles/{torrent_id}"
    body = {"files": torrent_file_id}

    async with aiohttp.ClientSession() as session:
        await session.post(api_url, headers=headers, data=body)


async def get_movie_rd_link(torrent_link, season_episode) -> str:
    torrent_id = await add_magnet_to_rd(torrent_link)
    print(f"Magnet added to RD. ID: {torrent_id}")

    if season_episode:
        print("Setting episode file for season/episode...")
        await set_file_rd(torrent_id, season_episode)
    else:
        print("Setting movie file...")
        await set_file_rd(torrent_id)

    for i in range(3):
        print("Waiting for RD link...")
        api_url = f"{root_url}/torrents/info/{torrent_id}"

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers=headers) as response:
                response_json = await response.json()

        if len(response_json["links"]) >= 1:
            print("RD link found.")
            break
        await asyncio.sleep(2)
        print("RD link isn't ready. Retrying...")

    download_link = response_json["links"][0]
    api_url = "{root_url}/unrestrict/link"
    body = {"link": download_link}

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, headers=headers, data=body) as response:
            response_json = await response.json()

    media_link = response_json["download"]
    print(f"RD link: {media_link}")
    return media_link


async def get_movie_rd_links(torrent_links: list[str], season_episode) -> list[str]:
    def __run(torrent_link):
        return asyncio.run(get_movie_rd_link(torrent_link, season_episode))

    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(executor.map(__run, torrent_links))
        return results
    return []
