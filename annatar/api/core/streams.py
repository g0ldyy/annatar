import asyncio
import math
import re
from collections import defaultdict
from itertools import chain
from typing import Optional

import structlog
from prometheus_client import Counter, Histogram

from annatar import human, instrumentation, jackett
from annatar.clients.cinemeta import MediaInfo, get_media_info
from annatar.database import db
from annatar.debrid.models import StreamLink
from annatar.debrid.providers import DebridService
from annatar.jackett_models import SearchQuery
from annatar.stremio import Stream, StreamResponse
from annatar.torrent import TorrentMeta

log = structlog.get_logger(__name__)

UNIQUE_SEARCHES: Counter = Counter(
    name="unique_searches",
    documentation="Unique stream search counter",
    registry=instrumentation.registry(),
)


async def _search(
    type: str,
    max_results: int,
    debrid: DebridService,
    imdb_id: str,
    season_episode: None | list[int] = None,
    indexers: None | list[str] = None,
) -> StreamResponse:
    if indexers is None:
        indexers = []
    if season_episode is None:
        season_episode = []
    if await db.unique_add("stream_request", f"{imdb_id}:{season_episode}"):
        log.debug("unique search")
        UNIQUE_SEARCHES.inc()

    media_info: Optional[MediaInfo] = await get_media_info(id=imdb_id, type=type)
    if not media_info:
        log.error("error getting media info", type=type, id=imdb_id)
        return StreamResponse(streams=[], error="Error getting media info")
    log.info("found media info", type=type, id=id, media_info=media_info.model_dump())

    q = SearchQuery(
        imdb_id=imdb_id,
        name=media_info.name,
        type=type,
        year=int(re.split(r"\D", (media_info.releaseInfo or ""))[0]),
    )

    if type == "series" and len(season_episode) == 2:
        q.season = season_episode[0]
        q.episode = season_episode[1]

    results = await jackett.search_indexers(search_query=q, indexers=indexers)
    log.info("found torrents", torrents=len(results))

    resolution_links: dict[str, list[StreamLink]] = defaultdict(list)
    total_links: int = 0
    total_processed: int = 0
    stop = asyncio.Event()
    async for link in debrid.get_stream_links(
        torrents=results,
        season_episode=season_episode,
        stop=stop,
        max_results=max_results,
    ):
        total_processed += 1
        resolution: str = TorrentMeta.parse_title(link.name).resolution

        if len(resolution_links[resolution]) >= math.ceil(max_results / 2):
            log.debug("max results for resolution", resolution=resolution)
            continue

        resolution_links[resolution].append(link)
        total_links += 1
        if total_links >= max_results:
            log.debug("max results total")
            stop.set()
            break

    log.debug(
        "found stream links", links=total_links, processed=total_processed, torrents=len(results)
    )
    sorted_links: list[StreamLink] = list(
        sorted(
            chain(*resolution_links.values()),
            key=lambda x: human.rank_quality(x.name),
            reverse=True,
        )
    )

    streams: list[Stream] = [map_stream_link(link=link, debrid=debrid) for link in sorted_links]

    return StreamResponse(streams=streams)


def map_stream_link(link: StreamLink, debrid: DebridService) -> Stream:
    meta: TorrentMeta = TorrentMeta.parse_title(link.name)
    torrent_name_parts: list[str] = [f"{meta.title}"]
    if type == "series":
        torrent_name_parts.append(
            f"S{str(meta.season[0]).zfill(1)}E{str(meta.episode[0]).zfill(2)}"
            if meta.season and meta.episode
            else ""
        )
        torrent_name_parts.append(f"{meta.episodeName}" if meta.episodeName else "")

    torrent_name: str = " ".join(torrent_name_parts)
    # squish the title portion before appending more parts
    meta_parts: list[str] = []
    if meta.resolution:
        meta_parts.append(f"📺{meta.resolution}")
    if meta.audio_channels:
        meta_parts.append(f"🔊{meta.audio_channels}")
    if meta.codec:
        meta_parts.append(f"{meta.codec}")
    if meta.quality:
        meta_parts.append(f"{meta.quality}")

    meta_parts.append(f"💾{human.bytes(float(link.size))}")

    name = f"[{debrid.short_name()}+] Annatar"
    name += f" {meta.resolution}" if meta.resolution else ""
    name += f" {meta.audio_channels}" if meta.audio_channels else ""

    return Stream(
        url=link.url.strip(),
        title="\n".join(
            [
                torrent_name,
                human.arrange_into_rows(strings=meta_parts, rows=2),
            ]
        ),
        name=name.strip(),
    )


REQUEST_DURATION = Histogram(
    name="api_request_duration_seconds",
    documentation="Duration of API requests in seconds",
    labelnames=["type", "debrid_service"],
    registry=instrumentation.registry(),
)


async def get_hashes(
    imdb_id: str,
    limit: int = 20,
    season: int | None = None,
    episode: int | None = None,
) -> list[db.ScoredItem]:
    cache_key: str = f"jackett:search:{imdb_id}"
    if not season and not episode:
        res = await db.unique_list_get_scored(f"{cache_key}:torrents")
        return res[:limit]
    if season and episode:
        cache_key += f":{season}:{episode}"
        res = await db.unique_list_get_scored(cache_key)
        return res[:limit]
    items: dict[str, db.ScoredItem] = {}
    cache_key += f":{season}:*"
    keys = await db.list_keys(f"{cache_key}:*")
    for values in asyncio.gather(asyncio.create_task(db.unique_list_get(key)) for key in keys):
        for value in values:
            items[value.value] = value
            if len(items) >= limit:
                return list(items.values())[:limit]
    return list(items.values())[:limit]


async def search(
    type: str,
    max_results: int,
    debrid: DebridService,
    imdb_id: str,
    season_episode: None | list[int] = None,
    indexers: None | list[str] = None,
) -> StreamResponse:
    if indexers is None:
        indexers = []
    if season_episode is None:
        season_episode = []
    with REQUEST_DURATION.labels(
        type=type,
        debrid_service=debrid.id(),
    ).time():
        try:
            return await _search(
                type=type,
                max_results=max_results,
                debrid=debrid,
                imdb_id=imdb_id,
                season_episode=season_episode,
                indexers=indexers,
            )
        except Exception as e:
            log.error("error searching", type=type, id=imdb_id, exc_info=e)
            return StreamResponse(streams=[], error="Error searching")
