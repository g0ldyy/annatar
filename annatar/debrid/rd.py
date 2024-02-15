import asyncio
from datetime import timedelta
from typing import Optional

import structlog

from annatar import human
from annatar.database import db
from annatar.debrid import real_debrid_api as api
from annatar.debrid.models import StreamLink
from annatar.debrid.rd_models import (
    InstantFile,
    TorrentFile,
    TorrentInfo,
    UnrestrictedLink,
)
from annatar.logging import timestamped
from annatar.torrent import Torrent

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


@timestamped()
async def select_torrent_file_by_season_episode(
    torrent_id: str,
    debrid_token: str,
    season_episode: list[int] = [],
):
    torrent_info: Optional[TorrentInfo] = await api.get_torrent_info(
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

    selected: bool = await api.select_torrent_file(
        debrid_token=debrid_token,
        file_id=str(torrent_file_id),
        torrent_id=torrent_id,
    )
    if selected:
        log.info("Selected torrent file", torrent_id=torrent_id, torrent_file_id=torrent_file_id)
    else:
        log.error(
            "Failed to select torrent file", torrent_id=torrent_id, torrent_file_id=torrent_file_id
        )


@timestamped()
async def get_torrent_link(info_hash: str, debrid_token: str) -> Optional[str]:
    torrents: list[TorrentInfo] = await api.list_torrents(debrid_token)

    log.info("Got torrent list", count=len(torrents))
    for torrent in torrents:
        if torrent.hash.lower() != info_hash.lower():
            continue
        if torrent.links:
            if torrent.status != "downloaded":
                log.error("torrent is not downloaded yet", status=torrent.status)
                return None
            link = torrent.links[0]
            log.info("Torrent link found", link=link, info_hash=info_hash)
            return link
        else:
            # this typically means that the torrent isn't actually instantaly available
            # despite rd saying so. Sucks, but it is what it is.
            log.error(
                "Torrent has no links. It is not instantly available after all...",
                torrent=torrent,
                info_hash=info_hash,
            )
            return None
    log.info("Torrent not found in list", info_hash=info_hash)
    return None


async def _get_stream_for_torrent(
    info_hash: str,
    file_id: str,
    debrid_token: str,
) -> Optional[UnrestrictedLink]:
    torrent: Optional[Torrent] = await db.get_model(f"torrent:{info_hash}", model=Torrent)
    if not torrent:
        log.error("cached torrent not found", info_hash=info_hash)
        return None

    torrent_id: Optional[str] = await api.add_magnet(
        magnet_link=torrent.url, debrid_token=debrid_token
    )

    if not torrent_id:
        log.info("no torrent id found")
        return None

    log.info("magnet added to RD", torrent_id=torrent_id)

    log.info("selecting media file in torrent", torrent_id=torrent_id, file_id=file_id)
    selected: bool = await api.select_torrent_file(
        torrent_id=torrent_id,
        debrid_token=debrid_token,
        file_id=file_id,
    )
    if selected:
        log.info("Selected torrent file", torrent_id=torrent_id, file_id=file_id)
    else:
        log.error("Failed to select torrent file", torrent_id=torrent_id, file_id=file_id)

    torrent_link: Optional[str] = await get_torrent_link(
        info_hash=torrent.info_hash,
        debrid_token=debrid_token,
    )
    if not torrent_link:
        log.info("no torrent link found")
        return None

    log.info("RD Cached links found", link=torrent_link)

    unrestricted_link: Optional[UnrestrictedLink] = await api.unrestrict_link(
        torrent=torrent,
        link=torrent_link,
        debrid_token=debrid_token,
    )
    if not unrestricted_link:
        log.info("no unrestrict link found")
        return None

    log.info("Unrestricted link found", link=unrestricted_link.download)
    return unrestricted_link


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
    cached_stream: Optional[StreamLink] = await db.get_model(cache_key, model=StreamLink)
    if cached_stream:
        log.info("Cached stream found", stream=cached_stream)
        return cached_stream

    unrestricted_link: Optional[UnrestrictedLink] = await _get_stream_for_torrent(
        info_hash=info_hash,
        file_id=file_id,
        debrid_token=debrid_token,
    )
    if not unrestricted_link:
        log.info("No unrestricted link found")
        return None

    sl: StreamLink = StreamLink(
        size=unrestricted_link.filesize,
        name=unrestricted_link.filename,
        url=unrestricted_link.download,
    )
    await db.set_model(cache_key, sl, ttl=timedelta(weeks=4))
    return sl


@timestamped()
async def get_stream_link(
    torrent: Torrent,
    debrid_token: str,
    season_episode: list[int] = [],
) -> Optional[StreamLink]:
    cached_files: list[InstantFile] = await api.get_instant_availability(
        torrent.info_hash,
        debrid_token,
    )
    if not cached_files:
        return None

    torrent_files: list[TorrentFile] = [
        TorrentFile(
            id=f.id,
            path=f.filename,
            bytes=f.filesize,
        )
        for f in cached_files
    ]
    file_id: int = await select_biggest_file(
        files=torrent_files,
        season_episode=season_episode,
    )
    file: Optional[InstantFile] = next((f for f in cached_files if f.id == file_id), None)
    if not file:
        log.error("This torrent doesn't have a file? WTF?", file_id=file_id, files=torrent_files)
        return None

    # this route has to match the route provided to provide the 302
    # XXX How to get root url?
    url: str = f"/rd/{debrid_token}/{torrent.info_hash}/{file_id}"
    # need this for lookup later
    await db.set_model(key=f"torrent:{torrent.info_hash}", model=torrent, ttl=timedelta(weeks=8))
    return StreamLink(
        size=file.filesize,
        name=file.filename,
        url=url,
    )


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
