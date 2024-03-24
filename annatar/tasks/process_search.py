import asyncio
from concurrent.futures import ThreadPoolExecutor

import structlog
from structlog.contextvars import bound_contextvars

from annatar.clients import cinemeta
from annatar.pubsub.events import TorrentSearchCriteria, TorrentSearchResult
from annatar.tasks.torrent_processor import process_search_result
from annatar.torrent import Category
from annatar.trackers.search import search_all

log = structlog.get_logger(__name__)


async def process_search(
    imdb: str,
    category: Category,
    season: int | None = None,
    episode: int | None = None,
):
    with bound_contextvars(imdb=imdb, category=category, season=season, episode=episode):
        media_info = await cinemeta.get_media_info(imdb, category)
        if not media_info:
            log.info("No media info found")
            return

        with ThreadPoolExecutor(max_workers=10) as executor:
            async for torrent in search_all(imdb, category, season, episode):
                log.info("processing torrent")
                executor.submit(
                    process_search_result,
                    TorrentSearchResult(
                        title=torrent.Title,
                        info_hash=torrent.InfoHash if torrent.InfoHash else "",
                        guid=torrent.Guid,
                        magnet_link=torrent.Link or "",
                        indexer=torrent.Indexer,
                        size=torrent.Size,
                        search_criteria=TorrentSearchCriteria(
                            category=category,
                            imdb=imdb,
                            query=media_info.name,
                            year=media_info.release_year or 0,
                        ),
                    ),
                )
        log.debug("completed search")


def _process_search_result(result: TorrentSearchResult):
    log.debug("Processing search result", result=result.title)
    loop = asyncio.new_event_loop()
    try:
        coro = process_search_result(result)
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        log.debug("completed search processing, closing loop")
        loop.close()
