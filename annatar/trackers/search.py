import asyncio
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
    if not db.try_lock(f"search:{imdb}:{category}:{season}:{episode}", timeout=timedelta(hours=1)):
        log.debug("search results are fresh, not searching again")
        return []

    media_info: cinemeta.MediaInfo | None = await cinemeta.get_media_info(imdb, category)
    if not media_info:
        return []

    results: list[asyncio.Task] = [
        asyncio.create_task(indexer.search(media_info, imdb, category, season, episode))
        for indexer in ALL
    ]

    return await asyncio.gather(*results)
