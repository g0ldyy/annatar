import asyncio
import json
import re
from datetime import timedelta
from os import getenv
from typing import Generic, Optional, Tuple, Type, TypeVar

import aiohttp
import structlog
from pydantic import BaseModel
from structlog.contextvars import bind_contextvars

from annatar import human
from annatar.debrid import magnet
from annatar.debrid import premiumize_api as api
from annatar.debrid.models import StreamLink
from annatar.debrid.pm_models import DirectDL, DirectDLResponse
from annatar.logging import timestamped
from annatar.torrent import Torrent

log = structlog.get_logger(__name__)


async def select_stream_file(
    files: list[DirectDL],
    season_episode: list[int],
) -> StreamLink | None:
    sorted_files: list[DirectDL] = sorted(files, key=lambda f: f.size, reverse=True)
    if len(sorted_files) == 0:
        return None
    if len(sorted_files) == 1 or not season_episode:
        """If there is only one file, or no season_episode is provided, return the first file"""
        f: DirectDL = sorted_files[0]
        return StreamLink(name=f.path.split("/")[-1], size=f.size, url=f.link)

    for file in sorted_files:
        path = file.path.split("/")[-1].lower()
        if human.match_season_episode(season_episode=season_episode, file=path):
            log.debug("path matches season and episode", path=path, season_episode=season_episode)
            return StreamLink(name=file.path.split("/")[-1], size=file.size, url=file.link)
    log.info("no file found for season and episode", season_episode=season_episode)
    return None


@timestamped()
async def get_stream_link(
    magnet_link: str,
    debrid_token: str,
    season_episode: list[int] = [],
) -> StreamLink | None:
    info_hash: str | None = magnet.get_info_hash(magnet_link)
    if not info_hash:
        log.error("magnet is not a valid magnet link", magnet_link=magnet_link)
        return None

    dl: Optional[DirectDLResponse] = await api.directdl(
        magnet_link=magnet_link,
        api_token=debrid_token,
        info_hash=info_hash,
    )

    if not dl or not dl.content:
        log.info("magnet has no cached content", info_hash=info_hash)
        return None

    return await select_stream_file(dl.content, season_episode)


@timestamped()
async def get_stream_links(
    torrents: list[Torrent],
    debrid_token: str,
    season_episode: list[int],
    max_results: int = 5,
) -> list[StreamLink]:
    """
    Generates a list of stream links for each torrent link.
    """

    links: dict[str, StreamLink] = {}
    tasks = [
        asyncio.create_task(
            get_stream_link(
                magnet_link=torrent.url,
                season_episode=season_episode,
                debrid_token=debrid_token,
            )
        )
        for torrent in torrents
    ]

    for task in asyncio.as_completed(tasks):
        link: Optional[StreamLink] = await task
        if link:
            links[link.url] = link
            if len(links) >= max_results:
                break

    # Cancel remaining tasks
    for task in tasks:
        if not task.done():
            task.cancel()

    return list(links.values())[:max_results]
