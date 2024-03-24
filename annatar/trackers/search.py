import asyncio
from datetime import timedelta
from typing import AsyncGenerator

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
) -> AsyncGenerator[SearchResult, None]:
    if not await db.try_lock(
        f"search:{imdb}:{category}:{season}:{episode}", timeout=timedelta(hours=1)
    ):
        log.debug("search results are fresh, not searching again")
        return

    media_info: cinemeta.MediaInfo | None = await cinemeta.get_media_info(imdb, category)
    if not media_info:
        return

    log.info("searching indexers", imdb=imdb, category=category, season=season, episode=episode)
    tasks = [
        asyncio.create_task(
            indexer.search(
                media_info,
                imdb,
                category,
                season,
                episode,
            )
        )
        for indexer in ALL
    ]
    log.debug("searching gathering search results")
    for torrents in asyncio.as_completed(tasks, timeout=30):
        log.error("got torrents", torrents=torrents)
        for t in torrents:
            yield t
