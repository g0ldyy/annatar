import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Callable

import structlog
from fastapi import Request, Response
from prometheus_client import Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

from annatar import instrumentation

log = structlog.get_logger(__name__)
request_id = ContextVar("request_id", default="MISSING")

REQUEST_DURATION = Histogram(
    name="request_duration_seconds",
    documentation="Duration of HTTP requests in seconds",
    labelnames=["method", "request_handler", "status"],
    registry=instrumentation.REGISTRY,
)


def get_route_handler(request: Request) -> str | None:
    for route in request.app.routes:
        match, _child_scope = route.matches(request.scope)
        # Enum value 2 represents the route template Match.FULL
        if match.value == 2:
            return route.name
    return None


class Metrics(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        start_time = datetime.now()
        resp: Response = await call_next(request)
        request_time = datetime.now() - start_time
        status_code = f"{str(resp.status_code)[0]}xx"
        handler = get_route_handler(request)
        method = request.method
        if handler:
            REQUEST_DURATION.labels(method, handler, status_code).observe(
                request_time.total_seconds()
            )
        return resp


class RequestID(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        clear_contextvars()
        rid: str = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id.set(rid)
        bind_contextvars(request_id=rid)
        return await call_next(request)


class RequestLogger(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        ll = log.bind(
            method=request.method,
            query=request.url.query,
            request_id=request_id.get(),
            remote=request.client.host if request.client else None,
        )

        start_time: datetime = datetime.now()
        ll.info("http_request")
        response: Response = await call_next(request)
        process_time = f"{(datetime.now() - start_time).total_seconds():.3f}s"
        response.headers["X-Process-Time"] = process_time
        response.headers["X-Request-ID"] = str(request_id.get())

        route = request.scope.get("route")
        path: str = route.path if route else request.url.path
        ll.info(
            "http_response",
            duration=process_time,
            status=response.status_code,
            path=path,
        )
        return response
