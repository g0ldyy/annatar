import os

import uvicorn
from prometheus_client import CollectorRegistry, multiprocess

from annatar import config, instrumentation
from annatar.logging import init as init_logging

instrumentation.init()
init_logging()

NUM_CORES: int = os.cpu_count() or 1
WORKERS = int(os.getenv("WORKERS") or 2 * NUM_CORES)


# setup prometheus multiprocess before anything else
if WORKERS > 1:
    multiprocess.MultiProcessCollector(CollectorRegistry())


if __name__ == "__main__":
    uvicorn.run(
        "annatar.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,
        workers=WORKERS,
        loop="uvloop",
        log_level="error",
    )
