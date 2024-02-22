from datetime import datetime, timedelta
from typing import Any, AsyncGenerator

import aiohttp
import structlog

from annatar import instrumentation
from annatar.database import db
from annatar.debrid import magnet
from annatar.debrid.rd_models import (
    InstantFile,
    InstantFileSet,
    TorrentInfo,
    UnrestrictedLink,
)

ROOT_URL = "https://api.real-debrid.com/rest/1.0"


log = structlog.get_logger(__name__)


async def make_request(
    method: str,
    debrid_token: str,
    url: str,
    url_values: dict[str, str] = {},
    body: dict[str, Any] = {},
) -> Any:
    api_url = f"{ROOT_URL}{url.format(**url_values)}"
    start_time = datetime.now()
    status_code: str = "2xx"
    error = False
    try:
        async with aiohttp.ClientSession() as session:
            api_headers = {"Authorization": f"Bearer {debrid_token}"}
            async with session.request(method, api_url, headers=api_headers, data=body) as response:
                status_code = f"{response.status//100}xx"
                if response.status not in range(200, 300):
                    error = True
                    log.error(
                        "Error making request",
                        status=response.status,
                        reason=response.reason,
                        url=api_url,
                        body=await response.text(),
                    )
                    return None
                response_json = await response.json()
                return response_json
    finally:
        instrumentation.HTTP_CLIENT_REQUEST_DURATION.labels(
            client="real_debrid",
            method=method,
            url=url,
            error=error,
            status_code=status_code,
        ).observe((datetime.now() - start_time).total_seconds())


async def add_magnet(info_hash: str, debrid_token: str) -> str | None:
    """
    Adds a magnet link to RD and returns the torrent id.
    """
    response_json = await make_request(
        method="post",
        url="/torrents/addMagnet",
        debrid_token=debrid_token,
        body={"magnet": magnet.make_magnet_link(info_hash=info_hash)},
    )
    return response_json["id"] if response_json else None


async def get_instant_availability(
    info_hash: str,
    debrid_token: str,
) -> AsyncGenerator[list[InstantFile], None]:
    NO_CACHE = "0"
    cache_key: str = f"rd:instantAvailable:{info_hash.upper()}"
    cached = await db.get(cache_key)
    if cached == NO_CACHE:
        log.debug("cached response: hash has no instantAvailability", info_hash=info_hash)
        raise StopAsyncIteration

    res = await make_request(
        method="GET",
        url="/torrents/instantAvailability/{info_hash}",
        url_values={"info_hash": info_hash},
        debrid_token=debrid_token,
    )
    if res is None:
        log.debug("no instantAvailability", info_hash=info_hash)
        await db.set(cache_key, NO_CACHE, ttl=timedelta(minutes=30))
        raise StopAsyncIteration

    for hash, obj in res.items():
        if hash.lower() != info_hash.lower():
            continue
        if "rd" not in obj:
            continue
        for set in obj.get("rd", []):
            cached_files = [
                InstantFile(id=int(file_id), **file_info) for file_id, file_info in set.items()
            ]
            log.info("found cached files", count=len(cached_files))
            await db.set_model(
                cache_key, InstantFileSet(files=cached_files), ttl=timedelta(minutes=30)
            )
            yield cached_files


async def list_torrents(debrid_token: str) -> list[TorrentInfo]:
    response_json = await make_request(
        method="GET",
        url="/torrents",
        debrid_token=debrid_token,
    )
    if not response_json:
        return []
    return [TorrentInfo(**t) for t in response_json]


async def get_torrent_info(
    torrent_id: str,
    debrid_token: str,
) -> TorrentInfo | None:
    response_json = await make_request(
        method="GET",
        url="/torrents/info/{torrent_id}",
        url_values={"torrent_id": torrent_id},
        debrid_token=debrid_token,
    )
    if not response_json:
        return None

    return TorrentInfo(**response_json)


async def select_torrent_files(
    torrent_id: str,
    file_ids: list[int],
    debrid_token: str,
    season_episode: list[int] = [],
) -> bool:
    await make_request(
        method="POST",
        url="/torrents/selectFiles/{torrent_id}",
        url_values={"torrent_id": torrent_id},
        debrid_token=debrid_token,
        body={"files": ",".join(str(f) for f in file_ids)},
    )
    return True


async def unrestrict_link(
    info_hash: str,
    link: str,
    debrid_token: str,
) -> UnrestrictedLink | None:
    response_json = await make_request(
        method="POST",
        url="/unrestrict/link",
        debrid_token=debrid_token,
        body={"link": link},
    )
    if not response_json:
        return None
    response_json["info_hash"] = info_hash
    unrestrict_info: UnrestrictedLink = UnrestrictedLink(**response_json)
    log.info("Got unrestrict link", link=unrestrict_info.link, info_hash=info_hash)
    return unrestrict_info


async def delete_torrent(torrent_id: str, debrid_token: str):
    response_json = await make_request(
        method="DELETE",
        url="/torrents/delete/{torrent_id}",
        url_values={"torrent_id": torrent_id},
        debrid_token=debrid_token,
    )
    if response_json:
        log.info("Deleted torrent", torrent_id=torrent_id)
