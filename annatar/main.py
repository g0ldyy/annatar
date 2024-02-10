from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.status import HTTP_204_NO_CONTENT

from annatar import logging, middleware, routes, web

logging.init()
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

log = structlog.get_logger(__name__)


# XXX These are executed in reverse order
app.add_middleware(middleware.RequestLogger)
app.add_middleware(middleware.RequestID)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://*.stremio.com"],
)


# handle CORS preflight requests
@app.options("/{rest_of_path:path}")
async def preflight_handler(request: Request, rest_of_path: str) -> Response:
    return Response(
        status_code=HTTP_204_NO_CONTENT,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
        },
    )


# set CORS headers
@app.middleware("http")
async def add_CORS_header(request: Request, call_next: Any):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    return response


app.include_router(routes.router)
app.include_router(web.router)
