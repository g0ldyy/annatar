from datetime import datetime
from typing import Any

import aiohttp
import structlog

from annatar import instrumentation
from annatar.debrid.rd_models import InstantFile, TorrentInfo, UnrestrictedLink
from annatar.torrent import Torrent

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
                status_code = f"{response.status//100}xx"  # type: ignore
                if response.status not in range(200, 300):
                    timer.labels(error="true")  # type: ignore
                    log.error(
                        "Error making request",
                        status=response.status,
                        reason=response.reason,
                        body=await response.text(),
                    )
                    return None
                response_json = await response.json()
                return response_json
    except Exception as e:
        log.error("Error making request", error=e)
        error = True
        return None
    finally:
        instrumentation.HTTP_CLIENT_REQUEST_DURATION.labels(
            client="real_debrid",
            method=method,
            url=url,
            error=error,
            status_code=status_code,
        ).observe((datetime.now() - start_time).total_seconds())


async def add_magnet(magnet_link: str, debrid_token: str) -> str | None:
    """
    Adds a magnet link to RD and returns the torrent id.
    """
    response_json = await make_request(
        method="post",
        url="/torrents/addMagnet",
        debrid_token=debrid_token,
        body={"magnet": magnet_link},
    )
    return response_json["id"] if response_json else None


async def get_instant_availability(info_hash: str, debrid_token: str) -> list[InstantFile]:
    res = await make_request(
        method="GET",
        url="/torrents/instantAvailability/{info_hash}",
        url_values={"info_hash": info_hash},
        debrid_token=debrid_token,
    )
    if not res:
        return []

    cached_files: list[InstantFile] = [
        InstantFile(id=int(id_key), **file_info)
        for value in res.values()
        if value
        for item in value.get("rd", [])
        for id_key, file_info in item.items()
    ]
    log.info("found cached files", count=len(cached_files))
    return cached_files


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


async def select_torrent_file(
    torrent_id: str,
    file_id: str,
    debrid_token: str,
    season_episode: list[int] = [],
) -> bool:
    await make_request(
        method="POST",
        url="/torrents/selectFiles/{torrent_id}",
        url_values={"torrent_id": torrent_id},
        debrid_token=debrid_token,
        body={"files": file_id},
    )
    return True


async def unrestrict_link(
    torrent: Torrent,
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
    response_json["torrent"] = torrent
    unrestrict_info: UnrestrictedLink = UnrestrictedLink(**response_json)
    log.info("Got unrestrict link", link=unrestrict_info.link, info_hash=torrent.info_hash)
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
