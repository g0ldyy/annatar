import os
from datetime import datetime

import uvicorn
from prometheus_client import CollectorRegistry, multiprocess

NUM_CORES: int = os.cpu_count() or 1
BUILD_VERSION: str = os.getenv("BUILD_VERSION", "UNKNOWN")
HOST: str = os.getenv("LISTEN_HOST", "0.0.0.0")
PORT: int = int(os.getenv("LISTEN_PORT", "8000"))
WORKERS = int(os.getenv("WORKERS", 2 * NUM_CORES))
PROM_DIR = os.getenv(
    "PROMETHEUS_MULTIPROC_DIR", f"/tmp/annatar.metrics-{datetime.now().timestamp()}"
)


if __name__ == "__main__":
    # setup prometheus multiprocess before anything else
    if WORKERS > 1:
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = PROM_DIR
        if not os.path.isdir(PROM_DIR):
            os.mkdir(PROM_DIR)
        multiprocess.MultiProcessCollector(CollectorRegistry())

    uvicorn.run(
        "annatar.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        workers=WORKERS,
        loop="uvloop",
        log_level="error",
    )
