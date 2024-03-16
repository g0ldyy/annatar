from datetime import datetime
from typing import Any, AsyncGenerator

import aiohttp
import structlog

from annatar import instrumentation, magnet
from annatar.debrid.rd_models import InstantFile, TorrentInfo, UnrestrictedLink

ROOT_URL = "https://api.real-debrid.com/rest/1.0"


log = structlog.get_logger(__name__)


async def make_request(
    method: str,
    debrid_token: str,
    url: str,
    source_ip: str | None = None,
    url_values: None | dict[str, str] = None,
    body: None | dict[str, Any] = None,
) -> Any:
    if body is None:
        body = {}
    if url_values is None:
        url_values = {}
    if source_ip and method == "POST":
        # set the origin IP for the user. RD asks for this for tracking purposes
        body["ip"] = source_ip
    api_url = f"{ROOT_URL}{url.format(**url_values)}"
    start_time = datetime.now()
    status_code: str = "2xx"
    error = False
    try:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with aiohttp.ClientSession() as session, session.request(
            method, api_url, headers=api_headers, data=body
        ) as response:
            status_code = f"{response.status//100}xx"
            if response.status in [401, 403]:
                log.warning(
                    "RD token is invalid",
                    status=response.status,
                    reason=response.reason,
                    url=api_url,
                    body=await response.text(),
                )
                return None
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
            return await response.json()
    finally:
        instrumentation.HTTP_CLIENT_REQUEST_DURATION.labels(
            client="real_debrid",
            method=method,
            url=url,
            error=error,
            status_code=status_code,
        ).observe((datetime.now() - start_time).total_seconds())


async def add_magnet(info_hash: str, debrid_token: str, source_ip: str) -> str | None:
    """
    Adds a magnet link to RD and returns the torrent id.
    """
    response_json = await make_request(
        method="POST",
        url="/torrents/addMagnet",
        debrid_token=debrid_token,
        body={"magnet": magnet.make_magnet_link(info_hash=info_hash)},
        source_ip=source_ip,
    )
    return response_json["id"] if response_json else None


async def get_instant_availability(
    info_hash: str,
    debrid_token: str,
) -> AsyncGenerator[list[InstantFile], None]:
    res = await make_request(
        method="GET",
        url="/torrents/instantAvailability/{info_hash}",
        url_values={"info_hash": info_hash},
        debrid_token=debrid_token,
    )
    if res is None:
        log.debug("No instant availability", info_hash=info_hash)
        return

    for hash, obj in res.items():
        if hash.lower() != info_hash.lower():
            continue
        if "rd" not in obj:
            continue
        for set in obj.get("rd", []):
            cached_files = [
                InstantFile(id=int(file_id), **file_info) for file_id, file_info in set.items()
            ]
            log.info("found cached files", count=len(cached_files), info_hash=info_hash)
            yield cached_files


async def list_torrents(debrid_token: str, page: int = 1, limit: int = 50) -> list[TorrentInfo]:
    response_json = await make_request(
        method="GET",
        url="/torrents",
        debrid_token=debrid_token,
        url_values={"page": str(page), "limit": str(limit)},
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
    source_ip: str,
    season_episode: None | list[int] = None,
) -> bool:
    if season_episode is None:
        season_episode = []
    await make_request(
        method="POST",
        url="/torrents/selectFiles/{torrent_id}",
        url_values={"torrent_id": torrent_id},
        debrid_token=debrid_token,
        body={"files": ",".join(str(f) for f in file_ids)},
        source_ip=source_ip,
    )
    return True


async def unrestrict_link(
    info_hash: str,
    link: str,
    debrid_token: str,
    source_ip: str,
) -> UnrestrictedLink | None:
    response_json = await make_request(
        method="POST",
        url="/unrestrict/link",
        debrid_token=debrid_token,
        body={"link": link},
        source_ip=source_ip,
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
