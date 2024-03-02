import asyncio
import math
from collections import defaultdict
from datetime import timedelta
from itertools import chain

import structlog
from prometheus_client import Counter, Histogram
from pydantic import ValidationError

from annatar import human, instrumentation
from annatar.database import db, odm
from annatar.debrid.models import StreamLink
from annatar.debrid.providers import DebridService
from annatar.pubsub import events
from annatar.stremio import Stream, StreamResponse
from annatar.torrent import Category, TorrentMeta

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
    resolutions: list[str],
    season_episode: None | list[int] = None,
) -> StreamResponse:
    if season_episode is None:
        season_episode = []
    if await db.unique_add("stream_request", f"{imdb_id}:{season_episode}"):
        log.debug("unique search")
        UNIQUE_SEARCHES.inc()

    await events.SearchRequest.publish(
        events.SearchRequest(
            imdb=imdb_id,
            category=Category(type),
        )
    )
    log.info("searching for stream links")

    stream_links: list[StreamLink] = await get_stream_links(
        debrid=debrid,
        imdb=imdb_id,
        max_results=max_results,
        resolutions=resolutions,
        season=season_episode[0] if len(season_episode) == 2 else 0,
        episode=season_episode[1] if len(season_episode) == 2 else 0,
    )

    log.info("got stream links", count=len(stream_links))
    sorted_links: list[StreamLink] = list(
        sorted(
            chain(stream_links),
            key=lambda x: human.rank_quality(x.name),
            reverse=True,
        )
    )

    streams: list[Stream] = [map_stream_link(link=link, debrid=debrid) for link in sorted_links]

    return StreamResponse(streams=streams)


async def get_stream_links(
    debrid: DebridService,
    imdb: str,
    max_results: int,
    resolutions: list[str],
    season: int = 0,
    episode: int = 0,
) -> list[StreamLink]:
    log.debug("getting stream links", imdb=imdb, max_results=max_results, resolutions=resolutions)

    # this is essentially a countdown. The timeout is how long the lock will be
    # held for. If we can lock it then we likely just kicked off a new search so
    # we should poll the database for new torrents. If we can't lock it then we
    # should only search once
    lock_key: str = f"stream_links:{imdb}:{season}:{episode}"
    tries = 5 if await db.try_lock(lock_key, timeout=timedelta(minutes=30)) else 1

    log.debug("searching for torrents", imdb=imdb, season=season, episode=episode, tries=tries)
    torrents: list[str] = []
    for i in range(1, tries + 1):
        if len(torrents) >= max_results * 2:
            break
        if i > 1:
            await asyncio.sleep(1)
        torrents = await odm.list_torrents(
            imdb=imdb,
            season=season,
            episode=episode,
            resolutions=resolutions,
        )
    log.debug("done searching for torrents", count=len(torrents))

    resolution_links: dict[str, list[StreamLink]] = defaultdict(list)
    total_links: int = 0
    total_processed: int = 0
    stop = asyncio.Event()
    async for link in debrid.get_stream_links(
        torrents=torrents,
        season=season,
        episode=episode,
        stop=stop,
        max_results=max_results,
    ):
        total_processed += 1
        resolution: str = ""
        try:
            resolution: str = TorrentMeta.parse_title(link.name).resolution
        except ValidationError as e:
            log.debug("error parsing title", title=link.name, exc_info=e)
            continue

        if len(resolution_links[resolution]) >= math.ceil(max_results / 3):
            log.debug("max results for resolution", resolution=resolution)
            continue

        resolution_links[resolution].append(link)
        total_links += 1
        if total_links >= max_results:
            log.debug("max results total")
            stop.set()
            break

    return list(chain.from_iterable(resolution_links.values()))


def map_stream_link(link: StreamLink, debrid: DebridService) -> Stream:
    meta: TorrentMeta = TorrentMeta.parse_title(link.name)

    meta_parts: list[str] = []
    if meta.resolution:
        meta_parts.append(f"📺{meta.resolution}")
    if meta.bitDepth:
        meta_parts.append(f"{meta.bitDepth}bit")
    if meta.hdr:
        meta_parts.append("HDR")
    if meta.audio_channels:
        meta_parts.append(f"🔊{meta.audio_channels}")
    if meta.codec:
        meta_parts.append(f"{meta.codec}")

    meta_parts.append(f"💾{human.bytes(float(link.size))}")

    name = f"[{debrid.short_name()}+] Annatar {debrid.short_name()}"
    name += f" {meta.resolution}" if meta.resolution else ""
    name += f" {meta.audio_channels}" if meta.audio_channels else ""

    return Stream(
        url=link.url.strip(),
        title="\n".join(
            [
                link.name.strip(),
                human.arrange_into_rows(strings=meta_parts, rows=3),
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
) -> list[str]:
    return await odm.list_torrents(
        imdb=imdb_id,
        season=season,
        episode=episode,
        limit=limit,
    )


async def search(
    type: str,
    max_results: int,
    debrid: DebridService,
    imdb_id: str,
    season_episode: None | list[int] = None,
    indexers: None | list[str] = None,
    resolutions: None | list[str] = None,
) -> StreamResponse:
    if indexers is None:
        indexers = []
    if season_episode is None:
        season_episode = []
    if resolutions is None:
        resolutions = []

    log.debug(
        "searching for content",
        type=type,
        id=imdb_id,
        season_episode=season_episode,
        indexers=indexers,
        resolutions=resolutions,
    )
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
                resolutions=resolutions,
            )
        except Exception as e:
            log.error("error searching", type=type, id=imdb_id, exc_info=e)
            return StreamResponse(streams=[], error="Error searching")
