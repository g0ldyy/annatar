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
REDIS_HOST = os.environ.get("REDIS_HOST", "")

if __name__ == "__main__":
    # setup prometheus multiprocess before anything else
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = PROM_DIR
    if not os.path.isdir(PROM_DIR):
        os.mkdir(PROM_DIR)
    multiprocess.MultiProcessCollector(CollectorRegistry())

    redis_server = None
    if not REDIS_HOST:
        import redislite

        redis_server = redislite.client.StrictRedis(serverconfig={"port": 6379})
        os.environ["REDIS_HOST"] = PROM_DIR

    uvicorn.run(
        "annatar.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        workers=WORKERS,
        loop="uvloop",
        log_level="error",
    )

    if redis_server:
        redis_server.close()
