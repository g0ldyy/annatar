import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from annatar.api import filters
from annatar.config import APP_ID, VERSION, UserConfig, parse_config
from annatar.debrid.providers import list_providers

router = APIRouter()
templates = Jinja2Templates(directory="templates")

log = structlog.get_logger()


class FormConfig(BaseModel):
    app_id: str = APP_ID
    version: str = VERSION
    available_filters: dict[str, list[filters.Filter]]
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
    model: FormConfig = FormConfig(
        user_config=config,
        available_filters={
            category: [x for x in filters.ALL if x.category == category]
            for category in set(f.category for f in filters.ALL)
        },
        available_debrid_providers=list_providers(),
    )
    return templates.TemplateResponse(
        request=request,
        name="configure.html.j2",
        context={"ctx": model.model_dump()},
    )
