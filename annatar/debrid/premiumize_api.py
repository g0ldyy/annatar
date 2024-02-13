from datetime import timedelta
from typing import Any, Generic, Optional, Type, TypeVar

import aiohttp
import structlog
from pydantic import BaseModel

from annatar.database import db
from annatar.debrid.pm_models import DirectDLResponse
from annatar.logging import timestamped

log = structlog.get_logger(__name__)


ROOT_URL = "https://www.premiumize.me/api"

T = TypeVar("T", bound=BaseModel)


class HTTPResponse(Generic[T]):
    model: T
    response: aiohttp.ClientResponse

    def __init__(self, model: T, response: aiohttp.ClientResponse):
        self.model = model
        self.response = response


@timestamped(["url", "method"])
async def make_request(
    api_token: str,
    url: str,
    method: str,
    model: Type[T],
    params: dict[str, str] = {},
    headers: dict[str, str] = {},
    data: Optional[dict[str, str]] = None,
) -> HTTPResponse[T]:
    full_url: str = f"{ROOT_URL}{url}"
    async with aiohttp.ClientSession() as session:
        params["apikey"] = api_token
        async with session.request(
            method=method,
            url=full_url,
            params=params,
            data=data,
            headers=headers,
        ) as response:
            raw: dict[str, Any] = await response.json()
            model_instance = model.model_validate(raw)
            return HTTPResponse(model=model_instance, response=response)


@timestamped(["magnet_link", "info_hash"])
async def directdl(
    magnet_link: str,
    api_token: str,
    info_hash: str,
) -> Optional[DirectDLResponse]:
    cache_key: str = f"premiumize:directdl:{info_hash}"
    cached: Optional[str] = await db.get(cache_key)
    if cached:
        return DirectDLResponse.model_validate_json(cached)

    dl_res: HTTPResponse[DirectDLResponse] = await make_request(
        api_token=api_token,
        method="POST",
        model=DirectDLResponse,
        url="/transfer/directdl",
        data={"src": magnet_link},
    )
    if dl_res.response.status not in range(200, 299):
        log.error(
            "failed to lookup directdl",
            info_hash=info_hash,
            status=dl_res.response.status,
            body=await dl_res.response.text(),
        )
        return None
    await db.set(key=cache_key, value=dl_res.model.model_dump_json(), ttl=timedelta(weeks=4))
    return dl_res.model
