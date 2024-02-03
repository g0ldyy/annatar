import json
import os
from base64 import b64decode
from enum import Enum
from typing import Annotated, Any, Optional

import structlog
from fastapi import APIRouter, HTTPException, Path
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from annatar import api, jackett, web
from annatar.debrid.providers import DebridService, get_provider, list_providers
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


@router.get("/manifest.json")
async def get_manifest() -> dict[str, Any]:
    return {
        "id": "community.blockloop.annatar",
        "icon": "https://i.imgur.com/p4V821B.png",
        "version": "0.1.0",
        "catalogs": [],
        "idPrefixes": ["tt"],
        "resources": ["stream"],
        "types": MediaType.all(),
        "name": "Annatar",
        "description": "Lord of Gifts. Search popular torrent sites and Debrid caches for streamable content.",
        "behaviorHints": {
            "configurable": "true",
            "configurationRequired": "true",
        },
    }


@router.get(
    "/api/form_config.json",
    response_model=web.FormConfig,
    response_model_exclude_none=False,
)
async def get_config() -> web.FormConfig:
    return web.FormConfig(
        availableIndexers=await jackett.get_indexers(),
        availableDebridProviders=list_providers(),
    )


@router.get(
    "/{b64config:str}/stream/{type:str}/{id:str}.json",
    response_model=StreamResponse,
    response_model_exclude_none=True,
)
async def search(
    type: MediaType,
    id: Annotated[str, Path(title="imdb ID", example="tt8927938", regex=r"tt\d+")],
    b64config: Annotated[str, Path(description="base64 encoded json blob")],
) -> StreamResponse:
    config: AppConfig = parse_config(b64config)
    debrid: Optional[DebridService] = get_provider(config.debrid_service, config.debrid_api_key)
    if not debrid:
        raise HTTPException(status_code=400, detail="Invalid debrid service")

    imdb_id: str = id.split(":")[0]
    season_episode: list[int] = [int(i) for i in id.split(":")[1:]]
    return await api.search(
        type=type,
        debrid=debrid,
        imdb_id=imdb_id,
        season_episode=season_episode,
        jackett_api_key=jackett_api_key,
        jackett_url=jackett_url,
        max_results=config.max_results,
    )


class AppConfig(BaseModel):
    debrid_service: str
    debrid_api_key: str
    max_results: int = 5


def parse_config(b64config: str) -> AppConfig:
    try:
        return AppConfig(**json.loads(b64decode(b64config)))
    except ValidationError as e:
        log.warning("error decoding config", error=e, errro_type=type(e).__name__)
        raise RequestValidationError(
            errors=e.errors(include_url=False, include_input=False),
        )
    except Exception as e:
        log.error("Unrecognized error", error=e)
        raise HTTPException(status_code=500, detail="Internal server error")
