import asyncio
import math
import re
from collections import defaultdict
from datetime import datetime
from itertools import chain
from typing import Optional

import structlog
from prometheus_client import Counter, Histogram

from annatar import human, instrumentation, jackett
from annatar.database import db
from annatar.debrid.models import StreamLink
from annatar.debrid.providers import DebridService
from annatar.jackett_models import SearchQuery
from annatar.meta.cinemeta import MediaInfo, get_media_info
from annatar.stremio import Stream, StreamResponse
from annatar.torrent import Torrent

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
    season_episode: list[int] = [],
    indexers: list[str] = [],
) -> StreamResponse:
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
        q.season = str(season_episode[0])
        q.episode = str(season_episode[1])

    torrents = await jackett.search_indexers(
        search_query=q,
        indexers=indexers,
    )

    resolution_links: dict[str, list[StreamLink]] = defaultdict(list)
    total_links: int = 0
    total_processed: int = 0
    stop = asyncio.Event()
    async for link in debrid.get_stream_links(
        torrents=torrents,
        season_episode=season_episode,
        stop=stop,
        max_results=max_results,
    ):
        total_processed += 1
        resolution: str = Torrent.parse_title(link.name).resolution

        if len(resolution_links[resolution]) >= math.ceil(max_results / 2):
            log.debug("max results for resolution", resolution=resolution)
            continue

        resolution_links[resolution].append(link)
        total_links += 1
        if total_links >= max_results:
            log.debug("max results total")
            break

    log.debug("found stream links", links=total_links, torrents=total_processed)
    sorted_links: list[StreamLink] = list(
        sorted(
            chain(*resolution_links.values()),
            key=lambda x: human.rank_quality(x.name),
            reverse=True,
        )
    )

    streams: list[Stream] = []
    for link in sorted_links:
        meta: Torrent = Torrent.parse_title(link.name)
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
        streams.append(
            Stream(
                url=link.url.strip(),
                title="\n".join(
                    [
                        torrent_name,
                        arrange_into_rows(strings=meta_parts, rows=2),
                    ]
                ),
                name=name.strip(),
            )
        )

    return StreamResponse(streams=streams)


def arrange_into_rows(strings: list[str], rows: int) -> str:
    split_index = (len(strings) + 1) // rows
    first_row = strings[:split_index]
    second_row = strings[split_index:]
    arranged_string = "\n".join([" ".join(first_row), " ".join(second_row)])
    return arranged_string


REQUEST_DURATION = Histogram(
    name="api_request_duration_seconds",
    documentation="Duration of API requests in seconds",
    labelnames=["type", "debrid_service", "cached", "error"],
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
    else:
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
    season_episode: list[int] = [],
    indexers: list[str] = [],
) -> StreamResponse:
    start_time = datetime.now()
    res: Optional[StreamResponse] = None
    try:
        res = await _search(
            type=type,
            max_results=max_results,
            debrid=debrid,
            imdb_id=imdb_id,
            season_episode=season_episode,
            indexers=indexers,
        )
        return res
    except Exception as e:
        log.error("error searching", type=type, id=imdb_id, exc_info=e)
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
