import asyncio
from typing import AsyncGenerator, Optional

import structlog

from annatar import human
from annatar.debrid import premiumize_api as api
from annatar.debrid.models import StreamLink
from annatar.debrid.pm_models import DirectDL, DirectDLResponse
from annatar.logging import timestamped

log = structlog.get_logger(__name__)


async def select_stream_file(
    files: list[DirectDL],
    season_episode: list[int],
) -> StreamLink | None:
    sorted_files: list[DirectDL] = sorted(files, key=lambda f: f.size, reverse=True)
    if len(sorted_files) == 0:
        return None
    if not season_episode:
        """No season_episode is provided, return the biggest file"""
        f: DirectDL = sorted_files[0]
        return StreamLink(name=f.path.split("/")[-1], size=f.size, url=f.link)

    for file in sorted_files:
        if not human.is_video(file.path):
            log.debug("file is not a video", file=file.path)
            continue

        path = file.path.split("/")[-1].lower()
        if human.match_season_episode(season_episode=season_episode, file=path):
            log.debug("path matches season and episode", path=path, season_episode=season_episode)
            return StreamLink(name=file.path.split("/")[-1], size=file.size, url=file.link)
    log.info("no file found for season and episode", season_episode=season_episode)
    return None


@timestamped()
async def get_stream_link(
    info_hash: str,
    debrid_token: str,
    season_episode: list[int] = [],
) -> StreamLink | None:
    log.info("searching for stream link", info_hash=info_hash, season_episode=season_episode)
    dl: Optional[DirectDLResponse] = await api.directdl(
        info_hash=info_hash,
        api_token=debrid_token,
    )

    if not dl or not dl.content:
        log.info("torrent has no cached content", info_hash=info_hash)
        return None

    return await select_stream_file(dl.content, season_episode)


@timestamped()
async def get_stream_links(
    torrents: AsyncGenerator[str, None],
    debrid_token: str,
    season_episode: list[int],
    max_results: int = 5,
) -> AsyncGenerator[StreamLink, None]:
    """
    Generates a list of stream links for each torrent link.
    """

    links: dict[str, StreamLink] = {}
    tasks = [
        asyncio.create_task(
            get_stream_link(
                info_hash=info_hash,
                season_episode=season_episode,
                debrid_token=debrid_token,
            )
        )
        async for info_hash in torrents
    ]

    for task in asyncio.as_completed(tasks):
        link: Optional[StreamLink] = await task
        if link and link.url not in links:
            log.info("got link from debrid", link=link.url)
            links[link.url] = link
            yield link
            if len(links) >= max_results:
                break

    log.debug("finished getting stream links", links=len(links), torrents=len(tasks))
