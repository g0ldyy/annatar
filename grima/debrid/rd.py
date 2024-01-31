import asyncio
import json
from os import getenv
from typing import Optional

import aiohttp
import structlog
from pydantic import BaseModel
from structlog.contextvars import bound_contextvars

from grima import human
from grima.debrid.models import StreamLink
from grima.debrid.rd_models import (
    InstantFile,
    StreamableFile,
    TorrentFile,
    TorrentInfo,
    UnrestrictedLink,
)
from grima.torrent import Torrent

ROOT_URL = "https://api.real-debrid.com/rest/1.0"


log = structlog.get_logger(__name__)


async def select_biggest_file(
    files: list[TorrentFile],
    season_episode: list[int],
) -> int:
    if len(files) == 0:
        log.debug("No files, returning 0")
        return 0
    sorted_files: list[TorrentFile] = sorted(files, key=lambda f: f.bytes, reverse=True)
    if len(files) == 1:
        log.debug("Only one file, returning", file=files[0])
        return files[0].id

    if not season_episode:
        log.info("No season_episode, returning", file=sorted_files[0])
        return sorted_files[0].id

    for file in sorted_files:
        path = file.path.lower()
        if human.match_season_episode(season_episode=season_episode, file=path):
            log.info(
                "found matched file for season/episode", file=file, season_episode=season_episode
            )
            return file.id
    log.info(
        "No file found for season/episode, returning first file",
        file=sorted_files[0],
        season_episode=season_episode,
    )
    return 0


async def add_link(magnet_link: str, debrid_token: str) -> str | None:
    api_url = f"{ROOT_URL}/torrents/addMagnet"
    body = {"magnet": magnet_link}

    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.post(api_url, headers=api_headers, data=body) as response:
            if response.status not in range(200, 300):
                log.error(
                    "Got status adding magnet to RD", status=response.status, magnet=magnet_link
                )
                return None
            response_json = await response.json()
            log.info("Magnet added to RD", torrent=response_json["id"], magnet=magnet_link)
            return response_json["id"]


async def get_instant_availability(info_hash: str, debrid_token: str) -> list[InstantFile]:
    api_url = f"{ROOT_URL}/torrents/instantAvailability/{info_hash}"
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.get(api_url, headers=api_headers) as response:
            if response.status not in range(200, 300):
                log.error(
                    "Error getting instant availability",
                    status=response.status,
                    reason=response.reason,
                    body=await response.text(),
                )
                return []
            res = await response.json()

    cached_files: list[InstantFile] = [
        InstantFile(id=int(id_key), **file_info)
        for value in res.values()
        if value
        for item in value.get("rd", [])
        for id_key, file_info in item.items()
    ]
    log.info("found cached files", count=len(cached_files))
    return cached_files


async def get_torrent_link(info_hash: str, debrid_token: str) -> str | None:
    api_url = f"{ROOT_URL}/torrents"
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.get(api_url, headers=api_headers) as response:
            if response.status not in range(200, 300):
                log.error(
                    "Error getting torrent list",
                    status=response.status,
                    reason=response.reason,
                    body=await response.text(),
                )
                return None
            response_json = await response.json()

    log.info("Got torrent list", count=len(response_json), info_hash=info_hash)
    for torrent in response_json:
        if torrent["hash"].lower() != info_hash.lower():
            continue
        links = torrent["links"]
        if links:
            link = links[0]
            log.info("Torrent link found", link=link, info_hash=info_hash)
            return link
        else:
            log.info("Torrent has no links", torrent=torrent, info_hash=info_hash)
            return None
    log.info("Torrent not found in list", info_hash=info_hash)
    return None


async def get_torrent_info(
    torrent_id: str,
    debrid_token: str,
) -> TorrentInfo | None:
    api_url = f"{ROOT_URL}/torrents/info/{torrent_id}"
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.get(api_url, headers=api_headers) as response:
            if response.status not in range(200, 300):
                log.error(
                    "Error getting torrent info",
                    status=response.status,
                    reason=response.reason,
                    body=await response.text(),
                )
                return None
            response_json = await response.json()
            torrent_info: TorrentInfo = TorrentInfo(**response_json)
            return torrent_info


async def select_torrent_file(
    torrent_id: str,
    debrid_token: str,
    season_episode: list[int] = [],
):
    torrent_info: TorrentInfo | None = await get_torrent_info(
        torrent_id=torrent_id,
        debrid_token=debrid_token,
    )

    if not torrent_info:
        log.info("No torrent info found", torrent_id=torrent_id)
        return

    torrent_files: list[TorrentFile] = torrent_info.files
    torrent_file_id = await select_biggest_file(files=torrent_files, season_episode=season_episode)
    log.info(
        "Selected file",
        torrent_id=torrent_id,
        torrent_file_id=torrent_file_id,
        season_episode=season_episode,
    )
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
                log.error(
                    "Error getting unrestrict link",
                    status=response.status,
                    reason=response.reason,
                    body=await response.text(),
                )
                return None
            unrestrict_response_json = await response.json()
            unrestrict_response_json["torrent"] = torrent
            unrestrict_info: UnrestrictedLink = UnrestrictedLink(**unrestrict_response_json)
            log.info("Got unrestrict link", link=unrestrict_info.link, info_hash=torrent.info_hash)
            return unrestrict_info


async def get_stream_link(
    torrent: Torrent,
    debrid_token: str,
    season_episode: list[int] = [],
) -> StreamLink | None:
    ll = log.bind(info_hash=torrent.info_hash, kind="series" if season_episode else "movie")
    cached_files: list[InstantFile] = await get_instant_availability(
        torrent.info_hash, debrid_token
    )
    if not cached_files:
        return None

    torrent_id = await add_link(magnet_link=torrent.url, debrid_token=debrid_token)
    if not torrent_id:
        ll.info("no torrent id found")
        return None

    ll.info("magnet added to RD")

    ll.info("selecting media file in torrent")
    await select_torrent_file(
        torrent_id=torrent_id, debrid_token=debrid_token, season_episode=season_episode
    )

    torrent_link: str | None = await get_torrent_link(
        info_hash=torrent.info_hash,
        debrid_token=debrid_token,
    )
    if not torrent_link:
        ll.info("no torrent link found")
        return None

    ll.info("RD Cached links found", link=torrent_link)

    unrestricted_link: UnrestrictedLink | None = await unrestrict_link(
        torrent=torrent,
        link=torrent_link,
        debrid_token=debrid_token,
    )
    if not unrestricted_link:
        ll.info("no unrestrict link found")
        return None
    return StreamLink(
        size=unrestricted_link.filesize,
        name=unrestricted_link.filename,
        url=unrestricted_link.download,
    )


async def delete_torrent(torrent_id: str, debrid_token: str):
    async with aiohttp.ClientSession() as session:
        api_url = f"{ROOT_URL}/torrents/delete/{torrent_id}"
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.delete(api_url, headers=api_headers) as response:
            log.info("Cleaned up torrent", torrent_id=torrent_id)


async def get_stream_links(
    torrents: list[Torrent],
    debrid_token: str,
    season_episode: list[int] = [],
    max_results: int = 5,
) -> list[StreamLink]:
    """
    Generates a list of RD links for each torrent link.
    """

    tasks = [
        get_stream_link(
            torrent=torrent,
            season_episode=season_episode,
            debrid_token=debrid_token,
        )
        for torrent in torrents
    ]
    return [r for r in await asyncio.gather(*tasks) if r]
