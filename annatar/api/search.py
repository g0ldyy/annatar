import asyncio
import contextlib
import os
from datetime import timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from annatar import stremio
from annatar.api.core import streams
from annatar.database import db, odm
from annatar.debrid.providers import all_providers, get_provider
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


DEBRID_PROVIDERS_REGEX = f"({'|'.join([p.id() for p in all_providers()])})"


@router.get("/cached/{debrid_service}/{category}/{imdb_id}")
async def search_cached_imdb(
    request: Request,
    imdb_id: Annotated[str, Path(description="IMDB ID", examples=["tt0120737"], regex=r"^tt\d+$")],
    category: Annotated[Category, Path(description="Category")],
    debrid_service: Annotated[
        str, Path(description="Debrid service", regex=DEBRID_PROVIDERS_REGEX)
    ],
    debrid_api_key: Annotated[str, Query(description="Debrid API key")],
    season: Annotated[int | None, Query(description="Season")] = None,
    episode: Annotated[int | None, Query(description="Episode")] = None,
    limit: Annotated[int, Query(description="Limit results per resolution", le=15, ge=1)] = 10,
) -> stremio.StreamResponse:
    debrid = get_provider(debrid_service, debrid_api_key, "")
    if not debrid:
        raise HTTPException(status_code=400, detail="Invalid debrid service")
    if category == Category.Series and (season is None or episode is None):
        raise HTTPException(
            status_code=400, detail="Season and episode must be provided with series"
        )

    resp = await streams.search(
        imdb_id=imdb_id,
        type=category,
        debrid=debrid,
        max_results=limit,
        season_episode=[season, episode] if season and episode else None,
    )
    for stream in resp.streams:
        if stream.url.startswith("/"):
            stream.url = f"{request.url.scheme}://{request.url.netloc}{stream.url}"
    return resp


@router.get("/imdb/{category}/{imdb_id}")
async def search_imdb(
    imdb_id: Annotated[str, Path(description="IMDB ID", examples=["tt0120737"], regex=r"^tt\d+$")],
    category: Annotated[Category, Path(description="Category", examples=["movie", "series"])],
    season: Annotated[int | None, Query(description="Season")] = None,
    episode: Annotated[int | None, Query(description="Episode")] = None,
    limit: Annotated[int, Query(description="Limit results")] = 10,
    timeout: Annotated[int, Query(description="Search timeout", le=10, ge=1)] = 10,
) -> MediaResponse:
    await events.SearchRequest.publish(
        request=events.SearchRequest(
            imdb=imdb_id,
            category=category,
            season=season,
            episode=episode,
        )
    )

    torrents: list[str] = await odm.list_torrents(
        imdb=imdb_id,
        season=season,
        episode=episode,
        limit=limit,
    )

    # check if the results are stale
    if not torrents and await db.try_lock(
        f"stream_links:{imdb_id}:{season}", timeout=timedelta(hours=1)
    ):
        with contextlib.suppress(asyncio.TimeoutError):
            torrents = await asyncio.wait_for(
                timeout=timeout,
                fut=wait_for_torrents(
                    imdb=imdb_id,
                    limit=limit,
                    season=season,
                    episode=episode,
                ),
            )

    mapped = await asyncio.gather(*[build_media(info_hash) for info_hash in torrents])
    return MediaResponse(media=[media for media in mapped if media is not None])


async def build_media(info_hash: str) -> None | Media:
    title = await odm.get_torrent_title(info_hash)
    if title is None:
        return None
    return Media(hash=info_hash, title=title)


async def wait_for_torrents(
    imdb: str, limit: int, season: int | None = None, episode: int | None = None
) -> list[str]:
    torrents: list[str] = []
    with contextlib.suppress(asyncio.TimeoutError):
        torrents = await odm.list_torrents(
            imdb=imdb,
            season=season,
            episode=episode,
            limit=limit,
        )
        while len(torrents) < limit:
            await asyncio.sleep(1)
            torrents = await odm.list_torrents(
                imdb=imdb,
                season=season,
                episode=episode,
                limit=limit,
            )
    return torrents
