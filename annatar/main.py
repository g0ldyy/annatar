import structlog
from fastapi import FastAPI

from annatar import logging, middleware, routes

logging.init()
app = FastAPI()

log = structlog.get_logger(__name__)


# XXX These are executed in reverse order
app.add_middleware(middleware.RequestLogger)
app.add_middleware(middleware.RequestID)

app.include_router(routes.router)
