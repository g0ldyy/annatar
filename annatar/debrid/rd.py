import asyncio
import json
from datetime import timedelta
from os import getenv
from typing import Optional

import aiohttp
import structlog
from pydantic import BaseModel
from structlog.contextvars import bound_contextvars

from annatar import human
from annatar.cache import CACHE
from annatar.debrid import real_debrid_api as api
from annatar.debrid.models import StreamLink
from annatar.debrid.rd_models import (
    InstantFile,
    StreamableFile,
    TorrentFile,
    TorrentInfo,
    UnrestrictedLink,
)
from annatar.logging import timestamped
from annatar.torrent import Torrent

ROOT_URL = "https://api.real-debrid.com/rest/1.0"


log = structlog.get_logger(__name__)


@timestamped()
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


@timestamped()
async def select_torrent_file_by_season_episode(
    torrent_id: str,
    debrid_token: str,
    season_episode: list[int] = [],
):
    torrent_info: TorrentInfo | None = await api.get_torrent_info(
        torrent_id=torrent_id,
        debrid_token=debrid_token,
    )

    if not torrent_info or not torrent_info.files:
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

    selected: bool = api.select_torrent_file(
        api_url=api_url,
        debrid_token=debrid_token,
        body=body,
    )
    if selected:
        log.info("Selected torrent file", torrent_id=torrent_id, torrent_file_id=torrent_file_id)
    else:
        log.error(
            "Failed to select torrent file", torrent_id=torrent_id, torrent_file_id=torrent_file_id
        )


@timestamped()
async def get_torrent_link(info_hash: str, debrid_token: str) -> str | None:
    torrents: list[TorrentInfo] = await api.list_torrents(debrid_token)

    log.info("Got torrent list", count=len(torrents))
    for torrent in torrents:
        if torrent.hash.lower() != info_hash.lower():
            continue
        if torrent.links:
            link = torrent.links[0]
            log.info("Torrent link found", link=link, info_hash=info_hash)
            return link
        else:
            log.info("Torrent has no links", torrent=torrent, info_hash=info_hash)
            return None
    log.info("Torrent not found in list", info_hash=info_hash)
    return None


async def _get_stream_for_torrent(
    info_hash: str,
    file_id: str,
    debrid_token: str,
) -> UnrestrictedLink | None:
    torrent: Optional[Torrent] = await CACHE.get_model(f"torrent:{info_hash}", model=type(Torrent))
    if not torrent:
        log.error("No cached torrent not found", info_hash=info_hash)
        return None

    torrent_id: str | None = await api.add_magnet(
        magnet_link=torrent.url, debrid_token=debrid_token
    )

    if not torrent_id:
        log.info("no torrent id found")
        return None

    log.info("magnet added to RD", torrent_id=torrent_id)

    log.info("selecting media file in torrent", torrent_id=torrent_id, file_id=file_id)
    selected: bool = api.select_torrent_file(
        torrent_id=torrent_id,
        debrid_token=debrid_token,
        file_id=file_id,
    )
    if selected:
        log.info("Selected torrent file", torrent_id=torrent_id, file_id=file_id)
    else:
        log.error("Failed to select torrent file", torrent_id=torrent_id, file_id=file_id)

    torrent_link: str | None = await get_torrent_link(
        info_hash=torrent.info_hash,
        debrid_token=debrid_token,
    )
    if not torrent_link:
        log.info("no torrent link found")
        return None

    log.info("RD Cached links found", link=torrent_link)

    unrestricted_link: UnrestrictedLink | None = await api.unrestrict_link(
        torrent=torrent,
        link=torrent_link,
        debrid_token=debrid_token,
    )
    if not unrestricted_link:
        log.info("no unrestrict link found")
        return None

    log.info("Unrestricted link found", link=unrestricted_link)


@timestamped()
async def get_stream_for_torrent(
    info_hash: str,
    file_id: str,
    debrid_token: str,
) -> Optional[StreamLink]:
    """
    Get the stream link for a torrent and file.
    """
    cache_key: str = f"torrent:{info_hash}:{file_id}"
    cached_stream: Optional[StreamLink] = await CACHE.get_model(cache_key, model=type(StreamLink))
    if cached_stream:
        log.info("Cached stream found", stream=cached_stream)
        return cached_stream

    unrestricted_link: UnrestrictedLink | None = await _get_stream_for_torrent(
        info_hash=info_hash,
        file_id=file_id,
        debrid_token=debrid_token,
    )
    if not unrestricted_link:
        log.info("No unrestricted link found")
        return None

    await CACHE.set_model(cache_key, unrestricted_link, ttl=timedelta(weeks=1))
    return StreamLink(
        size=unrestricted_link.filesize,
        name=unrestricted_link.filename,
        url=unrestricted_link.download,
    )


@timestamped()
async def get_stream_link(
    torrent: Torrent,
    debrid_token: str,
    season_episode: list[int] = [],
) -> StreamLink | None:
    cached_files: list[InstantFile] = await api.get_instant_availability(
        torrent.info_hash,
        debrid_token,
    )
    if not cached_files:
        return None


@timestamped()
async def get_stream_links(
    torrents: list[Torrent],
    debrid_token: str,
    season_episode: list[int] = [],
    max_results: int = 5,
    timeout: int = 10,
) -> list[StreamLink]:
    """
    Generates a list of RD links for each torrent link.
    """

    links: dict[str, StreamLink] = {}
    tasks = [
        asyncio.create_task(
            get_stream_link(
                torrent=torrent,
                season_episode=season_episode,
                debrid_token=debrid_token,
            )
        )
        for torrent in torrents
    ]

    for task in asyncio.as_completed(tasks, timeout=timeout):
        link: Optional[StreamLink] = await task
        if link:
            links[link.url] = link
            if len(links) >= max_results:
                break

    # Cancel remaining tasks
    for task in tasks:
        if not task.done():
            task.cancel()

    return list(links.values())
