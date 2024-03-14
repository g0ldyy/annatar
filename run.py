import asyncio
import os
import threading

import uvicorn
from prometheus_client import CollectorRegistry, multiprocess

from annatar import config, instrumentation
from annatar.logging import init as init_logging
from annatar.torrent import Category

instrumentation.init()
init_logging()

NUM_CORES: int = os.cpu_count() or 1
WORKERS = int(os.getenv("WORKERS") or 2 * NUM_CORES)


# setup prometheus multiprocess before anything else
if WORKERS > 1:
    multiprocess.MultiProcessCollector(CollectorRegistry())


def start_torrent_processor(worker_id: int) -> None:
    from annatar.pubsub.consumers.torrent_processor import TorrentProcessor

    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _ = worker_id
    loop.run_until_complete(TorrentProcessor.run(WORKERS))
    loop.close()


def start_community_cache_processor() -> None:
    from annatar.pubsub.consumers.community_cache import CommunityCacheProcessor

    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(CommunityCacheProcessor().run(WORKERS))
    loop.close()


def start_search_processor(indexer: str) -> None:
    from annatar.pubsub.consumers.torrent_search.base_jackett_processor import BaseJackettProcessor

    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    p = BaseJackettProcessor(
        indexer=indexer,
        supports_imdb=True,
        num_workers=WORKERS,
        queue_size=WORKERS * 5,
        categories=[Category.Movie, Category.Series],
    )
    loop.run_until_complete(p.run())
    loop.close()


if __name__ == "__main__":
    # Start Redis processor threads
    for worker_id in range(WORKERS):
        thread: threading.Thread = threading.Thread(
            target=start_torrent_processor,
            args=(worker_id,),
            daemon=True,
            name=f"torrent-processor-{worker_id}",
        )
        thread.start()

    if config.ENABLE_COMMUNITY_CACHE:
        thread: threading.Thread = threading.Thread(
            target=start_community_cache_processor,
            daemon=True,
            name="community-cache-processor",
        )
        thread.start()

    for worker_id, indexer in enumerate(config.JACKETT_INDEXERS_LIST):
        thread: threading.Thread = threading.Thread(
            target=start_search_processor,
            args=(indexer,),
            daemon=True,
            name=f"search-processor-{indexer}-{worker_id}",
        )
        thread.start()

    uvicorn.run(
        "annatar.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,
        workers=WORKERS,
        loop="uvloop",
        log_level="error",
    )
