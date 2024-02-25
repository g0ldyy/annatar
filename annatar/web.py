import asyncio
from datetime import timedelta

import aiohttp
import structlog
import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from annatar import jackett
from annatar.config import APP_ID, VERSION, UserConfig, parse_config
from annatar.database import db
from annatar.debrid.providers import list_providers

router = APIRouter()
templates = Jinja2Templates(directory="templates")

log = structlog.get_logger()


class Indexer(BaseModel):
    id: str
    name: str


class FormConfig(BaseModel):
    app_id: str = APP_ID
    version: str = VERSION
    available_indexers: list[Indexer]
    available_resolutions: list[str]
    available_debrid_providers: list[dict[str, str]]

    user_config: UserConfig


@router.get("/{b64config:str}/configure")
async def configure_existing(request: Request, b64config: str):
    config: UserConfig = parse_config(b64config)
    return await configure(request, config)


@router.get("/configure")
async def configure_new(request: Request):
    return await configure(request, UserConfig.defaults())


async def configure(request: Request, config: UserConfig) -> HTMLResponse:
    indexer_datas = zip(
        jackett.JACKETT_INDEXERS_LIST,
        await asyncio.gather(*[get_indexer_name(n) for n in jackett.JACKETT_INDEXERS_LIST]),
    )
    indexers: list[Indexer] = [Indexer(id=id, name=name) for id, name in indexer_datas]
    model: FormConfig = FormConfig(
        user_config=config,
        available_indexers=indexers,
        available_debrid_providers=list_providers(),
        available_resolutions=["4K", "QHD", "1080p", "720p", "480p"],
    )
    return templates.TemplateResponse(
        request=request,
        name="configure.html.j2",
        context={"ctx": model.model_dump()},
    )


async def get_indexer_name(id: str) -> str:
    cache_key = f"indexer:name:{id}"
    if cache := await db.get(cache_key):
        return cache

    url = f"https://raw.githubusercontent.com/Jackett/Jackett/aa44dc864975a2480aee979351c4284b6a49acf6/src/Jackett.Common/Definitions/{id}.yml"
    try:
        async with aiohttp.ClientSession() as session, session.get(url) as resp:
            if resp.status != 200:
                log.error("Failed to get indexer name", id=id, url=url, status=resp.status)
                return id
            raw = await resp.text()
            data = yaml.safe_load(raw)
            if name := data.get("name"):
                await db.set(cache_key, name, ttl=timedelta(days=30))
                return name
            log.error(
                "indexer name was not in response document",
                id=id,
                url=url,
                data=data,
                status_code=resp.status,
            )
            return id
    except Exception as e:
        log.error("Failed to get indexer name", id=id, url=url, exc_info=e)
    return id
