import re
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
import structlog
from pydantic import BaseModel

from annatar.database import db
from annatar.instrumentation import HTTP_CLIENT_REQUEST_DURATION

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

    @property
    def release_year(self) -> int | None:
        if not self.releaseInfo:
            return None

        # you'd think to split on - but you'd be wrong because cinemeta uses
        # an en-dash instead of a hyphen. Splitting on \D works for both cases
        if match := re.split(r"\D", self.releaseInfo):
            try:
                return int(match.pop())
            except ValueError:
                return None
        return None


async def _get_media_info(id: str, type: str) -> MediaInfo | None:
    api_url = f"https://v3-cinemeta.strem.io/meta/{type}/{id}.json"
    status = ""
    error = False
    start_time = datetime.now()
    try:
        async with aiohttp.ClientSession() as session, session.get(api_url) as response:
            status = f"{response.status // 100}xx"
            if response.status not in range(200, 300):
                log.error(
                    "Error retrieving MediaInfo from strem.io",
                    status=response.status,
                    reason=response.reason,
                    body=await response.text(),
                )
                error = True
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

            return MediaInfo(**meta)
    finally:
        HTTP_CLIENT_REQUEST_DURATION.labels(
            client="cinemeta",
            method="GET",
            url="/meta/{type}/{id}.json",
            status_code=status,
            error=error,
        ).observe(amount=(datetime.now() - start_time).total_seconds())


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
