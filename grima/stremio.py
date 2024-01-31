from typing import Optional

import aiohttp
import structlog
from pydantic import BaseModel

log = structlog.get_logger(__name__)


class Stream(BaseModel):
    name: str = "Jackett Debrid"
    title: str
    url: str


class StreamResponse(BaseModel):
    streams: list[Stream]
    error: str | None = None


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


async def get_media_info(id: str, type: str) -> MediaInfo | None:
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
            meta = response_json["meta"]
            media_info = MediaInfo(**meta)
            return media_info
