import os
from enum import Enum
from typing import Annotated, Any, Optional

import structlog
from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import RedirectResponse
from starlette.status import HTTP_302_FOUND

from annatar import api
from annatar.config import UserConfig, parse_config
from annatar.debrid.models import StreamLink
from annatar.debrid.providers import DebridService, get_provider
from annatar.debrid.real_debrid_provider import RealDebridProvider
from annatar.stremio import StreamResponse

router = APIRouter()

log = structlog.get_logger(__name__)

jackett_url: str = os.environ.get("JACKETT_URL", "http://localhost:9117")
jackett_api_key: str = os.environ.get("JACKETT_API_KEY", "")


class MediaType(str, Enum):
    movie = "movie"
    series = "series"

    def __str__(self):
        return self.value

    @staticmethod
    def all() -> list[str]:
        return [media_type.value for media_type in MediaType]


@router.get("/")
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/configure", status_code=HTTP_302_FOUND)


@router.get("/{b64config:str}/manifest.json")
async def get_manifst_with_config(request: Request) -> dict[str, Any]:
    return await get_manifest(request)


@router.get("/manifest.json")
async def get_manifest(request: Request) -> dict[str, Any]:
    return {
        "id": request.url.hostname,
        "icon": "https://i.imgur.com/p4V821B.png",
        "version": "0.1.0",
        "catalogs": [],
        "idPrefixes": ["tt"],
        "resources": ["stream"],
        "types": MediaType.all(),
        "name": "Annatar",
        "description": "Lord of Gifts. Search popular torrent sites and Debrid caches for streamable content.",
        "behaviorHints": {
            "configurable": True,
            "configurationRequired": False,
        },
    }


@router.get(
    "/rd/{debrid_api_key:str}/{info_hash:str}/{file_id:str}",
    response_model=StreamResponse,
    response_model_exclude_none=True,
)
async def get_rd_stream(
    debrid_api_key: Annotated[str, Path(description="Debrid token")],
    info_hash: Annotated[str, Path(description="Torrent info hash")],
    file_id: Annotated[str, Path(description="ID of the file in the torrent")],
) -> RedirectResponse:
    rd: RealDebridProvider = RealDebridProvider(debrid_api_key)
    stream: Optional[StreamLink] = await rd.get_stream_for_torrent(
        info_hash=info_hash,
        file_id=file_id,
        debrid_token=debrid_api_key,
    )
    if not stream:
        raise HTTPException(status_code=404, detail="No stream found")

    return RedirectResponse(url=stream.url, status_code=HTTP_302_FOUND)


@router.get(
    "/{b64config:str}/stream/{type:str}/{id:str}.json",
    response_model=StreamResponse,
    response_model_exclude_none=True,
)
async def list_streams(
    request: Request,
    type: MediaType,
    id: Annotated[
        str,
        Path(
            title="imdb ID",
            examples=["tt8927938", "tt0108778:5:8"],
            regex=r"tt\d+(:\d:\d)?",
        ),
    ],
    b64config: Annotated[str, Path(description="base64 encoded json blob")],
) -> StreamResponse:
    config: UserConfig = parse_config(b64config)
    debrid: Optional[DebridService] = get_provider(config.debrid_service, config.debrid_api_key)
    if not debrid:
        raise HTTPException(status_code=400, detail="Invalid debrid service")

    imdb_id: str = id.split(":")[0]
    season_episode: list[int] = [int(i) for i in id.split(":")[1:]]
    res: StreamResponse = await api.search(
        type=type,
        debrid=debrid,
        imdb_id=imdb_id,
        season_episode=season_episode,
        jackett_api_key=jackett_api_key,
        jackett_url=jackett_url,
        max_results=config.max_results,
        indexers=config.indexers,
    )

    for stream in res.streams:
        if stream.url.startswith("/"):
            stream.url = f"{request.url.scheme}://{request.url.netloc}{stream.url}"

    return res
