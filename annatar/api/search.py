import asyncio
import contextlib
import os
from datetime import timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Path, Query
from pydantic import BaseModel

from annatar.database import db, odm
from annatar.pubsub import events
from annatar.torrent import Category

router = APIRouter(prefix="/search", tags=["search"])

log = structlog.get_logger(__name__)


FORWARD_ORIGIN_IP = os.environ.get("FORWARD_ORIGIN_IP", "false").lower() == "true"
OVERRIDE_ORIGIN_IP = os.environ.get("OVERRIDE_ORIGIN_IP", None)
ORIGIN_IP_HEADER = os.environ.get("ORIGIN_IP_HEADER") or "X-Forwarded-For"


class Media(BaseModel):
    hash: str
    title: str


class MediaResponse(BaseModel):
    media: list[Media] = []


@router.get("/imdb/{category}/{imdb_id}")
async def root_redirect(
    imdb_id: Annotated[str, Path(description="IMDB ID", examples=["tt0120737"])],
    category: Annotated[Category, Path(description="Category", examples=["movie", "series"])],
    season: Annotated[int | None, Query(description="Season")] = None,
    episode: Annotated[int | None, Query(description="Episode")] = None,
    limit: Annotated[int, Query(description="Limit results")] = 10,
    timeout: Annotated[int, Query(description="Search timeout", lt=61, gt=1)] = 30,
) -> MediaResponse:
    await events.SearchRequest.publish(
        request=events.SearchRequest(
            imdb=imdb_id,
            category=category,
        )
    )
    lock_key: str = f"stream_links:{imdb_id}:{season}"
    is_stale = await db.try_lock(lock_key, timeout=timedelta(hours=1))

    if is_stale:
        # if the search is stale we need to wait for search results to come in
        q = asyncio.Queue[events.TorrentAdded]()
        pubsub_listener = events.TorrentAdded.listen(
            queue=q, consumer="search-torrent-added-listener"
        )

        async def queue_listener():
            while True:
                await q.get()

        with contextlib.suppress(asyncio.TimeoutError):
            tasks = [
                asyncio.create_task(pubsub_listener),
                asyncio.create_task(queue_listener()),
            ]
            await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.FIRST_EXCEPTION)
            for task in tasks:
                if not task.done():
                    task.cancel()

    torrents: list[str] = []
    timeout_time = asyncio.get_event_loop().time() + timeout
    while len(torrents) < limit:
        torrents = await odm.list_torrents(
            imdb=imdb_id,
            season=season,
            episode=episode,
            limit=limit,
        )
        if len(torrents) < limit:
            if asyncio.get_event_loop().time() > timeout_time:
                break
            await asyncio.sleep(1)

    mapped = await asyncio.gather(*[build_media(info_hash) for info_hash in torrents])
    return MediaResponse(media=[media for media in mapped if media is not None])


async def build_media(info_hash: str) -> None | Media:
    title = await odm.get_torrent_title(info_hash)
    if title is None:
        return None
    return Media(hash=info_hash, title=title)
