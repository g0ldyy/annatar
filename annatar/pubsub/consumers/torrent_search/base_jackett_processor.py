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

JACKETT_TIMEOUT = int(os.environ.get("JACKETT_TIMEOUT") or 7)
JACKETT_MAX_RESULTS = int(os.environ.get("JACKETT_MAX_RESULTS", 100))


class BaseJackettProcessor(BaseModel):
    indexer: str
    supports_imdb: bool
    categories: list[Category]

    async def process_message(
        self,
        request: SearchRequest,
        media_info: MediaInfo,
    ):
        log.debug("processing search request", request=request, indexer=self.indexer)
        tasks = [
            jackett.search_imdb(
                imdb=request.imdb,
                indexers=[self.indexer],
                category=request.category,
                timeout=JACKETT_TIMEOUT,
            ),
            jackett.search(
                query=media_info.name,
                indexers=[self.indexer],
                category=request.category,
                timeout=JACKETT_TIMEOUT,
            ),
        ]
        if request.season:
            tasks.append(
                jackett.search(
                    query=f"{media_info.name} S{request.season:02d}",
                    indexers=[self.indexer],
                    category=request.category,
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
            results, key=lambda x: self.prioritize_search_result(media_info, request, x)
        )
        for result in sorted_results[:JACKETT_MAX_RESULTS]:
            await self.publish_search_result(request, result, media_info)

    def prioritize_search_result(
        self, media_info: MediaInfo, request: SearchRequest, result: SearchResult
    ) -> tuple[int, int]:
        score = 5
        if TorrentMeta.parse_title(result.Title).matches_name(media_info.name):
            score -= 1
        if request.season and f"S{request.season:02d}" in result.Title:
            score -= 1
        if request.imdb and result.Imdb and f"tt{result.Imdb:07d}" == request.imdb:
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
