"""
This module is an Object-Document Mapper (ODM) for the Redis database. It
provides utility functions to store and retrieve keys information from the
database using uniform naming conventions and data structures.
"""

import sys
from datetime import timedelta

import structlog

from annatar import torrent
from annatar.database import db
from annatar.pubsub.events import TorrentAdded

log = structlog.get_logger(__name__)


class Keys:
    @staticmethod
    def torrent(info_hash: str) -> str:
        if not info_hash:
            raise ValueError("info_hash is required")
        return f"torrent:v1:meta:{info_hash.upper()}"

    @staticmethod
    def torrents(imdb: str, season: int | None = None, episode: int | None = None) -> str:
        if not imdb:
            raise ValueError("imdb is required")
        cache_key: str = f"torrents:v1:{imdb}"
        if season and episode:
            cache_key = f"{cache_key}:{season}:{episode}"
        elif season:
            cache_key = f"{cache_key}:{season}"
        return cache_key


async def add_torrent(
    info_hash: str,
    title: str,
    imdb: str,
    score: int,
    ttl: timedelta,
    season: int | None = None,
    episode: int | None = None,
) -> bool:
    added = await db.unique_list_add(
        name=Keys.torrents(imdb, season, episode),
        item=info_hash,
        score=score,
        ttl=ttl,
    )
    if added:
        log.debug("added torrent", info_hash=info_hash, title=title, imdb=imdb)
        await set_torrent_title(info_hash, title)
        await TorrentAdded.publish(
            TorrentAdded(
                info_hash=info_hash,
                title=title,
                imdb=imdb,
                season=season,
                episode=episode,
            )
        )
    return bool(added)


async def list_torrents(
    imdb: str,
    limit: int = sys.maxsize,
    season: int | None = None,
    episode: int | None = None,
    resolutions: list[str] | None = None,
) -> list[str]:
    keys = set([Keys.torrents(imdb, season, episode), Keys.torrents(imdb, season)])
    log.debug("looking up torrents", keys=keys, limit=limit)
    results: list[db.ScoredItem] = []
    for key in keys:
        for item in await db.unique_list_get_scored(name=key):
            if resolutions and torrent.get_resolution(item.score) not in resolutions:
                continue
            results.append(item)
            if len(results) >= limit:
                break

    log.info("found torrents", count=len(results))
    return list([item.value for item in sorted(results, key=lambda x: x.score, reverse=True)])


async def set_torrent_title(info_hash: str, title: str) -> bool:
    return await db.hset(Keys.torrent(info_hash), "title", title)


async def get_torrent_title(info_hash: str) -> str | None:
    meta = await get_torrent_meta(info_hash)
    return meta.get("title") if meta else None


async def set_torrent_meta(info_hash: str, meta: dict[str, str]) -> bool:
    return await db.hmset(Keys.torrent(info_hash), meta)


async def get_torrent_meta(info_hash: str) -> dict[str, str] | None:
    return await db.hgetall(Keys.torrent(info_hash))
