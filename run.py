import asyncio
import os
import threading
from datetime import datetime

import uvicorn
from prometheus_client import CollectorRegistry, multiprocess

from annatar import config
from annatar.logging import init as init_logging
from annatar.torrent import Category

NUM_CORES: int = os.cpu_count() or 1
BUILD_VERSION: str = os.getenv("BUILD_VERSION", "UNKNOWN")
HOST: str = os.getenv("LISTEN_HOST", "0.0.0.0")
PORT: int = int(os.getenv("LISTEN_PORT", "8000"))
WORKERS = int(os.getenv("WORKERS") or 2 * NUM_CORES)
PROM_DIR = os.getenv(
    "PROMETHEUS_MULTIPROC_DIR", f"/tmp/annatar.metrics-{datetime.now().timestamp()}"
)

init_logging()


def start_torrent_processor(worker_id: int) -> None:
    from annatar.pubsub.consumers.torrent_processor import TorrentProcessor

    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _ = worker_id
    loop.run_until_complete(TorrentProcessor.run(WORKERS))
    loop.close()


def start_search_processor(indexer: str, worker_id: int) -> None:
    from annatar.pubsub.consumers.torrent_search.base_jackett_processor import BaseJackettProcessor

    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _ = worker_id
    p = BaseJackettProcessor(
        indexer=indexer,
        supports_imdb=True,
        num_workers=WORKERS,
        queue_size=WORKERS * 2,
        categories=[Category.Movie, Category.Series],
    )
    loop.run_until_complete(p.run())
    loop.close()


if __name__ == "__main__":
    # setup prometheus multiprocess before anything else
    if WORKERS > 1:
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = PROM_DIR
        if not os.path.isdir(PROM_DIR):
            os.mkdir(PROM_DIR)
        multiprocess.MultiProcessCollector(CollectorRegistry())

    # Start Redis processor threads
    for worker_id in range(WORKERS):
        thread: threading.Thread = threading.Thread(
            target=start_torrent_processor,
            args=(worker_id,),
            daemon=True,
            name=f"torrent-processor-{worker_id}",
        )
        thread.start()

    for worker_id, indexer in enumerate(config.JACKETT_INDEXERS_LIST):
        thread: threading.Thread = threading.Thread(
            target=start_search_processor,
            args=(indexer, worker_id),
            daemon=True,
            name=f"search-processor-{indexer}-{worker_id}",
        )
        thread.start()

    uvicorn.run(
        "annatar.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        workers=WORKERS,
        loop="uvloop",
        log_level="error",
    )
