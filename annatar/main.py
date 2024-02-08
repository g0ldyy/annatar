import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from annatar import logging, middleware, routes, web

logging.init()
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

log = structlog.get_logger(__name__)


# XXX These are executed in reverse order
app.add_middleware(middleware.RequestLogger)
app.add_middleware(middleware.RequestID)

app.include_router(routes.router)
app.include_router(web.router)
