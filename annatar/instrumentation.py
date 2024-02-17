import os
from contextvars import ContextVar

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

REGISTRY = CollectorRegistry()
multiprocess.MultiProcessCollector(REGISTRY)
NO_CACHE = ContextVar("NO_CACHE", default=False)

Gauge(
    name="build_info",
    documentation="build information",
    multiprocess_mode="livemin",
    registry=REGISTRY,
    labelnames=["version"],
).labels(version=os.getenv("BUILD_VERSION", "UNKNOWN")).set(1)

HTTP_CLIENT_REQUEST_DURATION = Histogram(
    name="http_client_request_duration_seconds",
    documentation="Duration of Redis requests in seconds",
    labelnames=["client", "method", "url", "status_code", "error"],
    registry=REGISTRY,
)


async def metrics_handler(request: Request):
    data = generate_latest(REGISTRY)
    return Response(
        content=data,
        headers={
            "Content-Type": CONTENT_TYPE_LATEST,
            "Content-Length": str(len(data)),
        },
    )


def init():
    pass


def instrument_fastapi(app: FastAPI):
    pass
