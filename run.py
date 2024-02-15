import logging
import os
import sys

import uvicorn

NUM_CORES: int = os.cpu_count() or 1
BUILD_VERSION: str = os.getenv("BUILD_VERSION", "UNKNOWN")
HOST: str = os.getenv("LISTEN_HOST", "0.0.0.0")
PORT: int = int(os.getenv("LISTEN_PORT", "8000"))
WORKERS = int(os.getenv("WORKERS", 2 * NUM_CORES))
PROM_DIR = os.getenv("PROMETHEUS_MULTIPROC_DIR", f"/tmp/annatar.metrics-{os.getpid()}")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging._nameToLevel[LOG_LEVEL.upper()],  # type: ignore
)


if __name__ == "__main__":
    resource_attrs_raw: str = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")
    if resource_attrs_raw:
        resource_attrs: list[str] = resource_attrs_raw.split(",")
        resource_attrs.extend(
            [
                f"service.version={BUILD_VERSION}",
                "service.instance.id=annatar-vm",
            ]
        )
        os.environ["OTEL_RESOURCE_ATTRIBUTES"] = ",".join(resource_attrs)

    os.environ["PROMETHEUS_MULTIPROC_DIR"] = PROM_DIR
    os.mkdir(PROM_DIR)
    uvicorn.run(
        "annatar.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        workers=WORKERS,
        loop="uvloop",
        log_level=LOG_LEVEL,
    )
