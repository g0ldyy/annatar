import asyncio
from datetime import datetime, timezone
from itertools import chain

import structlog
from rq import Queue

from annatar import config
from annatar.clients import cinemeta, jackett
from annatar.clients.cinemeta import MediaInfo
from annatar.clients.jackett_models import SearchResult
from annatar.database import db
from annatar.indexers import curator
from annatar.pubsub.events import TorrentSearchCriteria, TorrentSearchResult
from annatar.torrent import Category, TorrentMeta

search_queue = Queue(f"annatar:{config.NAMESPACE}:search", connection=db.redis)

log = structlog.get_logger(__name__)


async def trigger_search(
    imdb: str,
    category: Category,
    season: int | None = None,
    episode: int | None = None,
):
    media_info: MediaInfo | None = await cinemeta.get_media_info(imdb, category.value)
    if not media_info:
        return

    # exponential backoff based on the age of the media in years
    now = datetime.now(tz=timezone.utc).year
    release_year = media_info.release_year or now
    age = now - release_year
    cache_time = config.JACKETT_CACHE_MINUTES * 2**age
    if not await db.try_lock(f"annatar:search:{imdb}", cache_time):
        log.debug("results are still fresh", imdb=imdb, release_year=media_info.release_year)
        return

    for indexer in config.JACKETT_INDEXERS_LIST:
        search_queue.enqueue(
            search_indexer,
            indexer,
            media_info,
            imdb,
            category,
            season,
            episode,
        )


async def search_indexer(
    indexer: str,
    media_info: MediaInfo,
    imdb: str,
    category: Category,
    season: int | None = None,
    episode: int | None = None,
):
    log.debug(
        "processing search request",
        indexer=indexer,
        imdb=imdb,
        category=category,
        season=season,
        episode=episode,
    )
    tasks = [
        jackett.search_imdb(
            imdb=imdb,
            indexers=[indexer],
            category=category,
            timeout=config.JACKETT_TIMEOUT,
        ),
        jackett.search(
            query=media_info.name,
            indexers=[indexer],
            category=category,
            timeout=config.JACKETT_TIMEOUT,
        ),
    ]
    if season:
        tasks.append(
            jackett.search(
                query=f"{media_info.name} S{season:02d}",
                indexers=[indexer],
                category=category,
                timeout=config.JACKETT_TIMEOUT,
            )
        )

    results = list(
        chain.from_iterable(
            r.Results for r in await asyncio.gather(*tasks, return_exceptions=False)
        )
    )
    log.debug("jackett search completed", request=len(results))

    sorted_results = sorted(
        results, key=lambda x: prioritize_search_result(media_info, imdb, x, season)
    )
    for result in sorted_results[: config.JACKETT_MAX_RESULTS]:
        queue_search_result(indexer, category, imdb, result, media_info)


def prioritize_search_result(
    media_info: MediaInfo, imdb: str, result: SearchResult, season: int | None
) -> tuple[int, int]:
    score = 5
    if TorrentMeta.parse_title(result.Title).matches_name(media_info.name):
        score -= 1
    if season and f"S{season:02d}" in result.Title:
        score -= 1
    if imdb and result.Imdb and f"tt{result.Imdb:07d}" == imdb:
        score -= 1
    return (score, result.Size * -1)


def queue_search_result(
    indexer,
    category: Category,
    imdb: str,
    result: SearchResult,
    media_info: MediaInfo,
):
    tsr = TorrentSearchResult(
        title=result.Title,
        info_hash=result.InfoHash if result.InfoHash else "",
        guid=result.Guid,
        magnet_link=result.Link or "",
        indexer=indexer,
        size=result.Size,
        search_criteria=TorrentSearchCriteria(
            category=category,
            imdb=imdb,
            query=media_info.name,
            year=media_info.release_year or 0,
        ),
    )

    curator.process(tsr)
