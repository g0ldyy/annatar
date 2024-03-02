import os
import re
from datetime import datetime, timedelta
from typing import Any, Type, TypeVar

import aiohttp
import structlog
from prometheus_client import Histogram
from pydantic import BaseModel
from structlog.contextvars import bound_contextvars

from annatar import instrumentation
from annatar.clients.jackett_models import SearchResponse
from annatar.database import db
from annatar.torrent import Category

log = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

JACKETT_API_KEY: str = os.environ.get("JACKETT_API_KEY", "")
JACKETT_CACHE_MINUTES = timedelta(minutes=int(os.environ.get("JACKETT_CACHE_MINUTES", "15")))
JACKETT_URL: str = os.environ.get("JACKETT_URL", "http://localhost:9117")

REQUEST_DURATION = Histogram(
    name="jackett_request_duration_seconds",
    documentation="Duration of Jackett requests in seconds",
    labelnames=["method", "indexer", "error"],
    registry=instrumentation.registry(),
)


class JackettSearchError(Exception):
    def __init__(self, message: str, status: int | None, body: str | None = None):
        self.message = message
        self.status = status
        self.body = body


async def search_imdb(
    imdb: str,
    category: Category,
    timeout: int,
    indexers: list[str],
) -> SearchResponse:
    """
    Search all indexers for torrents and insert them into the unique list
    by score
    """
    params = {
        "t": "movie" if category == "movie" else "tvsearch",
        "imdbid": imdb,
        "Category": category.id(),
        "Tracker[]": ",".join(indexers),
    }
    log.debug("searching jackett", indexers=indexers, imdb=imdb)
    start_time = datetime.now()
    error = None
    try:
        return (
            await make_request(
                url="/api/v2.0/indexers/all/results",
                params=params,
                timeout=timeout,
                model=SearchResponse,
            )
            or SearchResponse()
        )
    except Exception as e:
        log.error("jackett search failed", exc_info=e)
        error = e
        return SearchResponse()
    finally:
        REQUEST_DURATION.labels(
            method="indexer_search", indexer=",".join(indexers), error=error
        ).observe(
            amount=(datetime.now() - start_time).total_seconds(),
        )


async def search(
    query: str,
    category: Category,
    indexers: list[str],
    timeout: int,
) -> SearchResponse:
    """
    Search a single indexer for torrents and insert them into the unique list
    by score
    """
    sanitized_name: str = re.sub(r"\W", " ", query)
    params = {
        "Category": category.id(),
        "Query": f"{sanitized_name}",
        "Tracker[]": ",".join(indexers),
    }

    log.debug("searching jackett", indexers=",".join(indexers), query=query)
    start_time = datetime.now()
    error = None
    try:
        return (
            await make_request(
                url="/api/v2.0/indexers/all/results",
                params=params,
                timeout=timeout,
                model=SearchResponse,
            )
            or SearchResponse()
        )
    except Exception as e:
        log.error("jackett search failed", exc_info=e)
        error = e
        return SearchResponse()
    finally:
        REQUEST_DURATION.labels(
            method="indexer_search", indexer=",".join(indexers), error=error
        ).observe(
            amount=(datetime.now() - start_time).total_seconds(),
        )


async def make_request(
    url: str,
    params: dict[str, Any],
    timeout: int,
    model: Type[T],
) -> T | None:
    with bound_contextvars(
        url=url,
        params=params.copy(),
        timeout=timeout,
    ):
        cache_key: str = f"jackett:{url}:{params}"
        cached = await db.get_model(cache_key, model)
        if cached:
            log.debug("results are fresh", key=cache_key)
            return cached

        params["apikey"] = JACKETT_API_KEY
        log.debug("jackett request")
        async with aiohttp.ClientSession() as session, session.get(
            url=f"{JACKETT_URL}{url}",
            params=params,
            timeout=timeout,
            headers={"Accept": "application/json"},
        ) as response:
            if response.status == 200:
                raw: dict[str, Any] = await response.json()
                res = model.model_validate(raw)
                await db.set_model(cache_key, res, JACKETT_CACHE_MINUTES)
                return res

            body = await response.text()
            log.error(
                "jacket request failed with bad status code",
                status=response.status,
                reason=response.reason,
                body=body,
                exc_info=True,
            )
            raise JackettSearchError(
                f"Jackett request failed: {response.reason}",
                status=response.status,
                body=body,
            )
