import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from annatar import jackett
from annatar.config import APP_ID, UserConfig, parse_config
from annatar.debrid.providers import list_providers
from annatar.jackett_models import Indexer

router = APIRouter()
templates = Jinja2Templates(directory="templates")

log = structlog.get_logger()


class FormConfig(BaseModel):
    app_id: str = APP_ID
    available_indexers: list[Indexer]
    available_debrid_providers: list[dict[str, str]]

    user_config: UserConfig


@router.get("/{b64config:str}/configure")
async def configure_existing(request: Request, b64config: str):
    config: UserConfig = parse_config(b64config)
    return await configure(request, config)
    pass


@router.get("/configure")
async def configure_new(request: Request):
    return await configure(request, UserConfig.defaults())
    pass


async def configure(request: Request, config: UserConfig) -> HTMLResponse:
    model: FormConfig = FormConfig(
        user_config=config,
        available_indexers=await jackett.get_indexers(),
        available_debrid_providers=list_providers(),
    )
    return templates.TemplateResponse(
        request=request,
        name="configure.html.j2",
        context={"ctx": model.model_dump()},
    )
