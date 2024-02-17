import os
from contextvars import ContextVar

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)

log = structlog.get_logger()

NO_CACHE = ContextVar("NO_CACHE", default=False)


def registry() -> CollectorRegistry:
    reg = CollectorRegistry()
    multiprocess.MultiProcessCollector(reg)
    return reg


Gauge(
    name="build_info",
    documentation="build information",
    multiprocess_mode="livemin",
    labelnames=["version"],
    registry=registry(),
).labels(version=os.getenv("BUILD_VERSION", "UNKNOWN")).set(1)

HTTP_CLIENT_REQUEST_DURATION = Histogram(
    name="http_client_request_duration_seconds",
    documentation="Duration of Redis requests in seconds",
    labelnames=["client", "method", "url", "status_code", "error"],
    registry=registry(),
)


async def metrics_handler(request: Request):
    data = generate_latest(registry())
    return Response(
        content=data,
        headers={
            "Content-Type": CONTENT_TYPE_LATEST,
            "Content-Length": str(len(data)),
        },
    )


def init():
    return


def shutdown(app: FastAPI):
    log.info("shutdown prometheus multiprocess_mode")
    multiprocess.mark_process_dead(os.getpid())  # type: ignore
    return
