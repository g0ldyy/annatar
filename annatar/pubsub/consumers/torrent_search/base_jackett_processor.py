import asyncio
import os
from itertools import chain

import structlog
from pydantic import BaseModel

from annatar.clients import jackett
from annatar.clients.cinemeta import MediaInfo, get_media_info
from annatar.clients.jackett_models import SearchResult
from annatar.database import db
from annatar.pubsub.events import SearchRequest, TorrentSearchCriteria, TorrentSearchResult
from annatar.torrent import Category, TorrentMeta

log = structlog.get_logger(__name__)

JACKETT_TIMEOUT = 60
JACKETT_MAX_RESULTS = int(os.environ.get("JACKETT_MAX_RESULTS", 100))
JACKETT_TIMEOUT = int(os.environ.get("JACKETT_TIMEOUT", 60))


class BaseJackettProcessor(BaseModel):
    indexer: str
    supports_imdb: bool
    num_workers: int
    queue_size: int
    categories: list[Category]

    async def run(self):
        workers: list[asyncio.Task] = []
        while True:
            try:
                queue: asyncio.Queue[SearchRequest] = asyncio.Queue(maxsize=self.queue_size)

                workers = [
                    asyncio.create_task(
                        self.process_queue(queue),
                        name=f"{self.indexer}-search-processor-{i}",
                    )
                    for i in range(self.num_workers)
                ] + [asyncio.create_task(SearchRequest.listen(queue, self.indexer))]

                await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)
                log.error("search processor completed?", indexer=self.indexer)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.error("search processor stopped unexpectedly", indexer=self.indexer, exc_info=e)
                raise
            finally:
                for worker in workers:
                    if not worker.done():
                        worker.cancel()

    async def process_queue(self, queue: asyncio.Queue[SearchRequest]):
        while request := await queue.get():
            try:
                key = f"{self.indexer}-search-processor-{request.imdb}"
                if not await db.try_lock(key, jackett.JACKETT_CACHE_MINUTES):
                    continue
                media_info = await get_media_info(request.imdb, request.category)
                if not media_info:
                    continue
                await self.process_message(request, media_info)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.error("search processor stopped unexpectedly", indexer=self.indexer, exc_info=e)
                await asyncio.sleep(1)

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
