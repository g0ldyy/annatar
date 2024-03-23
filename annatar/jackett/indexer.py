import asyncio
import os
from itertools import chain

import structlog
from pydantic import BaseModel

from annatar.clients import jackett
from annatar.clients.cinemeta import MediaInfo
from annatar.clients.jackett_models import SearchResult
from annatar.pubsub.events import SearchRequest, TorrentSearchCriteria, TorrentSearchResult
from annatar.torrent import Category, TorrentMeta

log = structlog.get_logger(__name__)

JACKETT_TIMEOUT = int(os.environ.get("JACKETT_TIMEOUT") or 60)
JACKETT_MAX_RESULTS = int(os.environ.get("JACKETT_MAX_RESULTS", 100))


class JackettIndexer(BaseModel):
    indexer: str
    supports_imdb: bool
    categories: list[Category]

    async def search(
        self,
        media_info: MediaInfo,
        imdb: str,
        category: Category,
        season: int | None = None,
        episode: int | None = None,
    ) -> list[SearchResult]:
        with structlog.contextvars.bound_contextvars(
            imdb=imdb, category=category, season=season, episode=episode, indexer=self.indexer
        ):
            log.debug("processing search request")
            tasks = [
                jackett.search_imdb(
                    imdb=imdb,
                    indexers=[self.indexer],
                    category=category,
                    timeout=JACKETT_TIMEOUT,
                ),
                jackett.search(
                    query=media_info.name,
                    indexers=[self.indexer],
                    category=category,
                    timeout=JACKETT_TIMEOUT,
                ),
            ]
            if season:
                tasks.append(
                    jackett.search(
                        query=f"{media_info.name} S{season:02d}",
                        indexers=[self.indexer],
                        category=category,
                        timeout=JACKETT_TIMEOUT,
                    )
                )

            results = list(
                chain.from_iterable(
                    r.Results for r in await asyncio.gather(*tasks, return_exceptions=False)
                )
            )
            log.debug("jackett search completed", request=len(results))

            sorted_results = sorted(
                results,
                key=lambda result: self.prioritize_search_result(media_info, result, imdb, season),
            )
            return sorted_results[:JACKETT_MAX_RESULTS]

    def prioritize_search_result(
        self,
        media_info: MediaInfo,
        result: SearchResult,
        imdb: str,
        season: int | None = None,
    ) -> tuple[int, int]:
        score = 5
        if TorrentMeta.parse_title(result.Title).matches_name(media_info.name):
            score -= 1
        if season and f"S{season:02d}" in result.Title:
            score -= 1
        if imdb and result.Imdb and f"tt{result.Imdb:07d}" == imdb:
            score -= 1
        return (score, result.Size * -1)

    async def publish_search_result(
        self, request: SearchRequest, result: SearchResult, media_info: MediaInfo
    ):
        await TorrentSearchResult.publish(
            TorrentSearchResult(
                title=result.Title,
                info_hash=result.InfoHash if result.InfoHash else "",
                guid=result.Guid,
                magnet_link=result.Link or "",
                indexer=self.indexer,
                size=result.Size,
                search_criteria=TorrentSearchCriteria(
                    category=request.category,
                    imdb=request.imdb,
                    query=media_info.name,
                    year=media_info.release_year or 0,
                ),
            )
        )
