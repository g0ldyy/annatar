import re
from datetime import datetime, timedelta
from hashlib import md5
from typing import Optional

import structlog
from prometheus_client import Histogram

from annatar import human, instrumentation, jackett
from annatar.database import db
from annatar.debrid.models import StreamLink
from annatar.debrid.providers import DebridService
from annatar.jackett_models import Indexer, SearchQuery
from annatar.meta.cinemeta import MediaInfo, get_media_info
from annatar.stremio import Stream, StreamResponse
from annatar.torrent import Torrent

log = structlog.get_logger(__name__)


async def _search(
    type: str,
    max_results: int,
    jackett_url: str,
    jackett_api_key: str,
    debrid: DebridService,
    imdb_id: str,
    season_episode: list[int] = [],
    indexers: list[str] = [],
) -> StreamResponse:
    idx: str = "-".join(sorted(indexers))
    cache_key: str = f"api:search:{type}:{imdb_id}:{season_episode}:{debrid.id()}:{idx}"

    if not debrid.shared_cache():
        # since some debrid providers (RD) have to have goofy work arounds
        # for getting direct links we have to cache the results only for their
        # api key.
        hashed_api_key: str = md5(debrid.api_key.encode()).hexdigest()
        cache_key = f"{cache_key}:{hashed_api_key}"

    cached: Optional[StreamResponse] = await db.get_model(cache_key, StreamResponse)
    if cached:
        return StreamResponse(
            streams=cached.streams[:max_results],
            cached=True,
        )

    media_info: Optional[MediaInfo] = await get_media_info(id=imdb_id, type=type)
    if not media_info:
        log.error("error getting media info", type=type, id=imdb_id)
        return StreamResponse(streams=[], error="Error getting media info")
    log.info("found media info", type=type, id=id, media_info=media_info.model_dump())

    q = SearchQuery(
        name=media_info.name,
        type=type,
        year=int(re.split(r"\D", (media_info.releaseInfo or ""))[0]),
    )

    if type == "series" and len(season_episode) == 2:
        q.season = str(season_episode[0])
        q.episode = str(season_episode[1])

    torrents: list[Torrent] = await jackett.search_indexers(
        max_results=max(10, max_results),
        jackett_url=jackett_url,
        jackett_api_key=jackett_api_key,
        search_query=q,
        imdb=int(imdb_id.replace("tt", "")),
        timeout=60,
        indexers=[Indexer.find_by_id(i) for i in indexers],
    )

    links: list[StreamLink] = await debrid.get_stream_links(
        torrents=torrents,
        season_episode=season_episode,
        max_results=max_results,
    )

    sorted_links: list[StreamLink] = list(
        sorted(
            links,
            key=lambda x: human.score_by_quality(x.name),
            reverse=True,
        )
    )

    streams: list[Stream] = [
        Stream(
            title="\n".join(
                [
                    link.name,
                    f"💾{human.bytes(float(link.size))}",
                ]
            ),
            url=link.url,
            name=f"[{debrid.short_name()}+] {human.grep_quality(link.name)}",
        )
        for link in sorted_links
    ]
    resp = StreamResponse(streams=streams)
    await db.set_model(cache_key, resp, ttl=timedelta(days=7))
    return resp


REQUEST_DURATION = Histogram(
    name="api_request_duration_seconds",
    documentation="Duration of API requests in seconds",
    labelnames=["type", "debrid_service", "cached", "error"],
    registry=instrumentation.REGISTRY,
)


async def search(
    type: str,
    max_results: int,
    jackett_url: str,
    jackett_api_key: str,
    debrid: DebridService,
    imdb_id: str,
    season_episode: list[int] = [],
    indexers: list[str] = [],
) -> StreamResponse:
    start_time = datetime.now()
    res: Optional[StreamResponse] = None
    try:
        res = await _search(
            type=type,
            max_results=max_results,
            jackett_url=jackett_url,
            jackett_api_key=jackett_api_key,
            debrid=debrid,
            imdb_id=imdb_id,
            season_episode=season_episode,
            indexers=indexers,
        )
        return res
    except Exception as e:
        log.error("error searching", type=type, id=imdb_id, error=str(e))
        res = StreamResponse(streams=[], error="Error searching")
        return res
    finally:
        secs = (datetime.now() - start_time).total_seconds()
        REQUEST_DURATION.labels(
            type=type,
            debrid_service=debrid.id(),
            cached=res.cached if res else False,
            error=True if res and res.error else False,
        ).observe(
            secs,
            exemplar={
                "imdb": imdb_id,
                "season_episode": ",".join([str(i) for i in season_episode]),
            },
        )
