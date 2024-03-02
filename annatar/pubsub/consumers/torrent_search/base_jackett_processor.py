import asyncio
import os

import structlog
from pydantic import BaseModel

from annatar.clients import jackett
from annatar.clients.cinemeta import MediaInfo, get_media_info
from annatar.clients.jackett_models import SearchResponse, SearchResult
from annatar.database import db
from annatar.pubsub.events import SearchRequest, TorrentSearchCriteria, TorrentSearchResult
from annatar.torrent import Category

log = structlog.get_logger(__name__)

JACKETT_TIMEOUT = 60
JACKETT_MAX_RESULTS = int(os.environ.get("JACKETT_MAX_RESULTS", 100))
JACKETT_TIMEOUT = int(os.environ.get("JACKETT_TIMEOUT", 6))


class BaseJackettProcessor(BaseModel):
    indexer: str
    supports_imdb: bool
    num_workers: int
    queue_size: int
    categories: list[Category]

    async def run(self):
        queue: asyncio.Queue[SearchRequest] = asyncio.Queue(maxsize=self.queue_size)

        workers = [
            asyncio.create_task(
                self.process_queue(queue),
                name=f"{self.indexer}-search-processor-{i}",
            )
            for i in range(self.num_workers)
        ] + [asyncio.create_task(SearchRequest.listen(queue, self.indexer))]

        await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)

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
                await process_message(self, request, media_info)
            except asyncio.CancelledError:
                return


async def process_message(
    processor: BaseJackettProcessor,
    request: SearchRequest,
    media_info: MediaInfo,
):
    log.debug("processing search request", request=request, indexer=processor.indexer)
    results: SearchResponse = SearchResponse()
    if processor.supports_imdb:
        results = await jackett.search_imdb(
            imdb=request.imdb,
            indexers=[processor.indexer],
            category=request.category,
            timeout=JACKETT_TIMEOUT,
        )

    if not results.Results:
        results = await jackett.search(
            query=media_info.name,
            indexers=[processor.indexer],
            category=request.category,
            timeout=JACKETT_TIMEOUT,
        )

    log.debug("jackett search completed", request=len(results.Results))

    for result in results.Results[:JACKETT_MAX_RESULTS]:
        await publish_search_result(request, result, media_info)


async def publish_search_result(
    request: SearchRequest, result: SearchResult, media_info: MediaInfo
):
    await TorrentSearchResult.publish(
        TorrentSearchResult(
            title=result.Title,
            info_hash=result.InfoHash if result.InfoHash else "",
            guid=result.Guid,
            magnet_link=result.Link or "",
            search_criteria=TorrentSearchCriteria(
                category=request.category,
                imdb=request.imdb,
                query=media_info.name,
                year=media_info.release_year or 0,
            ),
        )
    )
