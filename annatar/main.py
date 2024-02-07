from asyncio import Task
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from annatar import logging, middleware, routes
from annatar.db import db

logging.init()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task: Task[None] = await db.init()
    yield
    log.info("executing shutdown tasks")
    task.cancel(msg="shutting down")


app = FastAPI(lifespan=lifespan)


log = structlog.get_logger(__name__)


# XXX These are executed in reverse order
app.add_middleware(middleware.RequestLogger)
app.add_middleware(middleware.RequestID)

app.include_router(routes.router)
