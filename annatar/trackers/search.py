import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import structlog

from annatar import config
from annatar.clients import cinemeta
from annatar.clients.jackett_models import SearchResult
from annatar.database import db
from annatar.jackett.indexer import JackettIndexer
from annatar.torrent import Category

log = structlog.get_logger(__name__)


ALL = [
    JackettIndexer(
        indexer=indexer,
        supports_imdb=True,
        categories=[Category.Movie, Category.Series],
    )
    for indexer in config.JACKETT_INDEXERS_LIST
]


async def search_all(
    imdb: str,
    category: Category,
    season: int | None = None,
    episode: int | None = None,
) -> list[SearchResult]:
    if not await db.try_lock(
        f"search:{imdb}:{category}:{season}:{episode}", timeout=timedelta(hours=1)
    ):
        log.debug("search results are fresh, not searching again")
        return []

    media_info: cinemeta.MediaInfo | None = await cinemeta.get_media_info(imdb, category)
    if not media_info:
        return []

    log.info("searching indexers", imdb=imdb, category=category, season=season, episode=episode)
    with ThreadPoolExecutor(max_workers=20) as executor:
        loop = asyncio.get_event_loop()
        results: list[asyncio.Future] = [
            loop.run_in_executor(
                executor,
                _search_one,
                media_info,
                indexer,
                imdb,
                category,
                season,
                episode,
            )
            for indexer in ALL
        ]
        log.debug("searching gathering search results")
        return await asyncio.gather(*results)


def _search_one(
    media_info: cinemeta.MediaInfo,
    indexer: JackettIndexer,
    imdb: str,
    category: Category,
    season: int | None = None,
    episode: int | None = None,
):
    loop = asyncio.new_event_loop()
    try:
        coro = indexer.search(
            media_info=media_info,
            imdb=imdb,
            category=category,
            season=season,
            episode=episode,
        )
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
