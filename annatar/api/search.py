import asyncio
import os
from typing import Annotated

import structlog
from fastapi import APIRouter, Path, Query
from pydantic import BaseModel

from annatar.database import odm
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
    season: Annotated[int | None, Query(description="Season", defualt=None)] = None,
    episode: Annotated[int | None, Query(description="Episode", defualt=None)] = None,
    limit: Annotated[int, Query(description="Limit results", defualt=10)] = 10,
    instant: Annotated[bool, Query(description="Instant results only", defualt=True)] = True,
) -> MediaResponse:
    await events.SearchRequest.publish(
        request=events.SearchRequest(
            imdb=imdb_id,
            category=category,
        )
    )
    torrents: list[str] = await odm.list_torrents(
        imdb=imdb_id,
        season=season,
        episode=episode,
        limit=limit,
    )
    if len(torrents) == 0:
        if instant:
            return MediaResponse(media=[])
        await asyncio.sleep(5)
        torrents = await odm.list_torrents(
            imdb=imdb_id,
            season=season,
            episode=episode,
            limit=limit,
        )
        if len(torrents) == 0:
            return MediaResponse(media=[])

    mapped = await asyncio.gather(*[build_media(info_hash) for info_hash in torrents])
    return MediaResponse(media=[media for media in mapped if media is not None])


async def build_media(info_hash: str) -> None | Media:
    title = await odm.get_torrent_title(info_hash)
    if title is None:
        return None
    return Media(hash=info_hash, title=title)
