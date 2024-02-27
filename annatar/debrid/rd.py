import asyncio
from datetime import timedelta
from hashlib import sha256
from typing import AsyncGenerator, Optional

import structlog

from annatar import human
from annatar.database import db
from annatar.debrid import real_debrid_api as api
from annatar.debrid.models import StreamLink
from annatar.debrid.rd_models import (
    InstantFile,
    InstantFileSet,
    TorrentFile,
    TorrentInfo,
    UnrestrictedLink,
)

ROOT_URL = "https://api.real-debrid.com/rest/1.0"


log = structlog.get_logger(__name__)


async def find_streamable_file_id(
    files: list[TorrentFile],
    season_episode: None | list[int] = None,
) -> int | None:
    if len(files) == 0:
        log.debug("No files, returning 0")
        return None

    video_files: list[TorrentFile] = [file for file in files if human.is_video(file.path)]
    if len(video_files) < 1:
        log.debug("release has no video files")
        return None

    sorted_files: list[TorrentFile] = sorted(video_files, key=lambda f: f.bytes, reverse=True)
    if not season_episode:
        log.debug("returning biggest file", file=sorted_files[0])
        return sorted_files[0].id if human.is_video(sorted_files[0].path) else None

    for file in sorted_files:
        path = file.path.lower()
        if human.match_season_episode(season_episode=season_episode, file=path):
            if not human.is_video(path):
                continue
            log.info(
                "found matched file for season/episode", file=file, season_episode=season_episode
            )
            return file.id
    log.info(
        "No file found for season/episode",
        season_episode=season_episode,
    )
    return None


async def get_torrent_link(
    torrent_id: str,
    file_id: int,
    info_hash: str,
    debrid_token: str,
) -> str | None:
    for attempt in range(5):
        torrent: TorrentInfo | None = await api.get_torrent_info(torrent_id, debrid_token)
        if not torrent:
            log.error("torrent info wasn't found")
            await asyncio.sleep(attempt * 0.5)
            continue

        if torrent.status != "downloaded":
            log.error("torrent is not downloaded yet", status=torrent.status)
            await asyncio.sleep(attempt * 0.5)
            continue

        if not torrent.files:
            log.error("torrent has no files")
            return None

        selected_files: list[int] = [f.id for f in torrent.files if f.selected]
        for i, fid in enumerate(selected_files):
            if fid == file_id:
                return torrent.links[i]

    log.error(
        "couldn't get instant torrent content",
        torrent_id=torrent_id,
        file_id=file_id,
        info_hash=info_hash,
    )
    return None


async def _get_stream_for_torrent(
    info_hash: str,
    file_id: int,
    debrid_token: str,
    source_ip: str,
) -> Optional[UnrestrictedLink]:
    file_set: InstantFileSet | None = await db.get_model(
        key=f"rd:instant_file_set:torrent:{info_hash.upper()}:{file_id}",
        model=InstantFileSet,
    )

    if not file_set:
        log.error("cached torrent not found", info_hash=info_hash)
        return None

    torrent_id: Optional[str] = await api.add_magnet(
        info_hash=info_hash,
        debrid_token=debrid_token,
        source_ip=source_ip,
    )

    if not torrent_id:
        log.info("no torrent id found")
        return None

    log.info("magnet added to RD", torrent_id=torrent_id)

    log.info("selecting instant file set in torrent", torrent_id=torrent_id, file_id=file_id)
    selected: bool = await api.select_torrent_files(
        torrent_id=torrent_id,
        debrid_token=debrid_token,
        file_ids=file_set.file_ids,
        source_ip=source_ip,
    )
    if selected:
        log.info("Selected torrent file set", torrent_id=torrent_id, file_id=file_id)
    else:
        log.error("Failed to select torrent file set", torrent_id=torrent_id, file_id=file_id)

    torrent_link: str | None = await get_torrent_link(
        torrent_id=torrent_id,
        file_id=file_id,
        info_hash=info_hash,
        debrid_token=debrid_token,
    )
    if not torrent_link:
        log.info("no torrent link found")
        return None

    log.info("RD Cached links found", link=torrent_link)

    unrestricted_link: Optional[UnrestrictedLink] = await api.unrestrict_link(
        info_hash=info_hash,
        link=torrent_link,
        debrid_token=debrid_token,
        source_ip=source_ip,
    )
    if not unrestricted_link:
        log.info("no unrestrict link found")
        return None

    log.info("Unrestricted link found", link=unrestricted_link.download)
    return unrestricted_link


async def get_stream_for_torrent(
    info_hash: str,
    file_id: int,
    debrid_token: str,
    source_ip: str,
) -> Optional[StreamLink]:
    """
    Get the stream link for a torrent and file.
    """
    key_hash: str = sha256(debrid_token.encode()).hexdigest()
    cache_key: str = f"rd:torrent:{info_hash}:{key_hash}:{file_id}"
    cached_stream: Optional[StreamLink] = await db.get_model(cache_key, model=StreamLink)
    if cached_stream:
        log.info("Cached stream found", stream=cached_stream)
        return cached_stream

    unrestricted_link: Optional[UnrestrictedLink] = await _get_stream_for_torrent(
        info_hash=info_hash,
        file_id=file_id,
        debrid_token=debrid_token,
        source_ip=source_ip,
    )
    if not unrestricted_link:
        log.info("No unrestricted link found")
        return None

    sl: StreamLink = StreamLink(
        size=unrestricted_link.filesize,
        name=unrestricted_link.filename,
        url=unrestricted_link.download,
    )
    await db.set_model(cache_key, sl, ttl=timedelta(hours=4))
    return sl


async def get_stream_link(
    info_hash: str,
    debrid_token: str,
    season_episode: None | list[int] = None,
) -> StreamLink | None:
    async for cached_files in api.get_instant_availability(
        info_hash,
        debrid_token,
    ):
        if not cached_files:
            continue

        torrent_files: list[TorrentFile] = [
            TorrentFile(
                id=f.id,
                path=f.filename,
                bytes=f.filesize,
            )
            for f in cached_files
        ]
        file_id: int | None = await find_streamable_file_id(
            files=torrent_files,
            season_episode=season_episode,
        )

        if not file_id:
            log.debug("set does not contain a suitable file")
            continue

        file: InstantFile | None = next((f for f in cached_files if f.id == file_id), None)
        if not file:
            log.error(
                "cached file set does not contain the desired file_id. This should not be possible",
                torrent=info_hash,
                file_id=file_id,
            )
            return None

        log.debug("found matching instantAvailable set")
        # this route has to match the route provided to provide the 302
        url: str = f"/rd/{debrid_token}/{info_hash}/{file_id}"

        await db.set_model(
            key=f"rd:instant_file_set:torrent:{info_hash.upper()}:{file_id}",
            model=InstantFileSet(file_ids=[f.id for f in cached_files]),
            ttl=timedelta(hours=8),
        )

        return StreamLink(
            size=file.filesize,
            name=file.filename,
            url=url,
        )
    return None


async def get_stream_links(
    torrents: list[str],
    debrid_token: str,
    stop: asyncio.Event,
    max_results: int,
    season_episode: None | list[int] = None,
) -> AsyncGenerator[StreamLink, None]:
    """
    Generates a list of RD links for each torrent link.
    """
    concurrency = max_results * 3
    grouped = [torrents[i : i + concurrency] for i in range(0, len(torrents), concurrency)]

    for group in grouped:
        if stop.is_set():
            return
        tasks = [
            asyncio.create_task(
                get_stream_link(
                    info_hash=info_hash,
                    season_episode=season_episode,
                    debrid_token=debrid_token,
                )
            )
            for info_hash in group
        ]

        for task in asyncio.as_completed(tasks):
            link = await task
            if link:
                yield link
            if stop.is_set():
                return
