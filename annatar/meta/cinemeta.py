from datetime import timedelta
from typing import Optional

import aiohttp
import structlog
from pydantic import BaseModel

from annatar.database import db
from annatar.logging import timestamped

log = structlog.get_logger(__name__)


class MediaInfo(BaseModel):
    id: str
    type: str
    name: str

    genres: Optional[list[str]] = None
    director: Optional[list[str]] = None
    cast: Optional[list[str]] = None
    poster: Optional[str] = None
    posterShape: Optional[str] = None
    background: Optional[str] = None
    logo: Optional[str] = None
    description: Optional[str] = None
    # A.k.a. year, e.g. "2000" for movies and "2000-2014" or "2000-" for TV shows
    releaseInfo: Optional[str] = ""
    imdbRating: Optional[str] = None
    # ISO 8601, e.g. "2010-12-06T05:00:00.000Z"
    released: Optional[str] = None
    runtime: Optional[str] = None
    language: Optional[str] = None
    country: Optional[str] = None
    awards: Optional[str] = None
    website: Optional[str] = None


@timestamped(["id", "type"])
async def _get_media_info(id: str, type: str) -> MediaInfo | None:
    async with aiohttp.ClientSession() as session:
        api_url = f"https://v3-cinemeta.strem.io/meta/{type}/{id}.json"
        async with session.get(api_url) as response:
            if response.status not in range(200, 300):
                log.error(
                    "Error retrieving MediaInfo from strem.io",
                    status=response.status,
                    reason=response.reason,
                    body=await response.text(),
                )
                return None
            response_json = await response.json()
            meta = response_json.get("meta", None)
            if not meta:
                log.info(
                    "meta field is missing from response_json. Probably no results",
                    api_url=api_url,
                    response_json=response_json,
                )
                return None

            media_info = MediaInfo(**meta)
            return media_info


async def get_media_info(id: str, type: str) -> Optional[MediaInfo]:
    cache_key = f"cinemeta:{type}:{id}"

    cached_result: Optional[MediaInfo] = await db.get_model(cache_key, model=MediaInfo)
    if cached_result:
        return cached_result

    res: Optional[MediaInfo] = await _get_media_info(id=id, type=type)
    if res is None:
        return None

    await db.set(
        cache_key,
        res.model_dump_json(),
        ttl=timedelta(days=30),
    )
    return res
