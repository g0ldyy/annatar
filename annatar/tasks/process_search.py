import asyncio
from concurrent.futures import ThreadPoolExecutor

import structlog

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
    media_info = await cinemeta.get_media_info(imdb, category)
    if not media_info:
        log.info("No media info found", imdb=imdb, category=category)
        return

    log.info("Searching for torrent", imdb=imdb, category=category, season=season, episode=episode)
    torrents = await search_all(imdb, category, season, episode)

    max_workers: int = 10
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        loop = asyncio.get_running_loop()
        await asyncio.gather(
            loop.run_in_executor(
                executor,
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
            for torrent in torrents
        )
