import asyncio
import os
from datetime import timedelta
from itertools import product

import aiohttp
import structlog
from rq import Queue

from annatar import config, magnet
from annatar.database import db, odm
from annatar.pubsub.events import TorrentSearchCriteria, TorrentSearchResult
from annatar.torrent import Category, Torrent, TorrentMeta

log = structlog.get_logger(__name__)

MAGNET_RESOLVE_TIMEOUT = int(os.getenv("MAGNET_RESOLVE_TIMEOUT", "30"))
TORRENT_PROCESSOR_MAX_QUEUE_DEPTH = int(os.getenv("TORRENT_PROCESSOR_MAX_QUEUE_DEPTH", "10000"))

_curator_queue: Queue = Queue(f"curator-{config.NAMESPACE}", connection=db.redis)


def process(result: TorrentSearchResult):
    _curator_queue.enqueue(_process, result)


async def _process(result: TorrentSearchResult):
    # XXX If title.endswith("..."): search title with hashlists.info
    criteria = result.search_criteria
    if result.imdb and criteria.imdb and result.imdb != criteria.imdb:
        log.info("skipping mismatched IMDB", wanted=criteria.imdb, got=result.imdb)
        return
    torrent: Torrent | None = await map_search_result(result)
    if not torrent:
        return

    if result.imdb != criteria.imdb and not torrent.matches_name(criteria.query):
        log.info("skipping mismatched title", wanted=criteria.query, got=torrent.title)
        return

    ttl = timedelta(weeks=8)
    if result.search_criteria.category == Category.Movie:
        await process_movie(torrent, result.indexer, result.size, criteria, ttl)
    else:
        await process_show(torrent, result.indexer, result.size, criteria, ttl)


async def process_movie(
    torrent: Torrent,
    indexer: str,
    size: int,
    criteria: TorrentSearchCriteria,
    ttl: timedelta,
):
    score = torrent.match_score(title=torrent.title, year=criteria.year)
    if score > 0:
        await odm.add_torrent(
            info_hash=torrent.info_hash,
            title=torrent.raw_title,
            imdb=criteria.imdb,
            score=score,
            size=size,
            ttl=ttl,
            indexer=indexer,
            category=Category.Movie,
        )


async def process_show(
    torrent: Torrent,
    indexer: str,
    size: int,
    criteria: TorrentSearchCriteria,
    ttl: timedelta,
):
    if not torrent.episode:
        for season in torrent.season:
            score = torrent.match_score(title=torrent.title, year=criteria.year, season=season)
            await odm.add_torrent(
                info_hash=torrent.info_hash,
                title=torrent.raw_title,
                imdb=criteria.imdb,
                score=score,
                ttl=ttl,
                season=season,
                category=Category.Series,
                indexer=indexer,
                size=size,
            )
    elif torrent.season:
        for season, episode in product(torrent.season, torrent.episode):
            score = torrent.match_score(
                title=torrent.title,
                year=criteria.year,
                season=season,
                episode=episode,
            )
            if score > 0:
                await odm.add_torrent(
                    info_hash=torrent.info_hash,
                    title=torrent.raw_title,
                    imdb=criteria.imdb,
                    score=score,
                    ttl=ttl,
                    season=season,
                    episode=episode,
                    category=Category.Series,
                    indexer=indexer,
                    size=size,
                )


async def map_search_result(result: TorrentSearchResult) -> Torrent | None:
    info_hash: str | None = (
        result.info_hash
        if result.info_hash
        else (
            await resolve_magnet_link(
                guid=result.guid,
                link=result.magnet_link,
            )
        )
    )

    if info_hash:
        meta: TorrentMeta = TorrentMeta.parse_title(result.title)
        torrent: Torrent = meta.with_info_hash(info_hash)
        return torrent
    log.debug("no info hash found", guid=result.guid, link=result.magnet_link)
    return None


async def resolve_magnet_link(guid: str, link: str) -> str | None:
    """
    Jackett sometimes does not have a magnet link but a local URL that
    redirects to a magnet link. This will not work if adding to RD and
    Jackett is not publicly hosted. Most of the time we can resolve it
    locally. If not we will just pass it along to RD anyway
    """
    if link.startswith("magnet"):
        return magnet.parse_magnet_link(link)
    if not link.startswith("http"):
        return None

    cache_key: str = f"magnet:resolve:{guid}"
    try:
        info_hash: str | None = await db.get(cache_key)
        if info_hash:
            return info_hash

        log.debug("magnet resolve: following redirect", guid=guid, link=link)
        async with aiohttp.ClientSession() as session, session.get(
            link,
            allow_redirects=False,
            timeout=MAGNET_RESOLVE_TIMEOUT,
        ) as response:
            if response.status != 302:
                log.warn("magnet resolve: no redirect found", guid=guid, status=response.status)
                return None

            location = response.headers.get("Location", "")
            if not location:
                return None

            info_hash = magnet.parse_magnet_link(location)
            log.debug("magnet resolve: found redirect", info_hash=info_hash, location=location)
            await db.set(cache_key, info_hash, ttl=timedelta(weeks=8))
            return info_hash
    except TimeoutError:
        log.warn("magnet resolve: timeout")
        return None
    except asyncio.exceptions.CancelledError:
        log.debug("magnet resolve: cancelled")
        return None
    except Exception as err:
        log.error("magnet resolve error", exc_info=err)
        return None
