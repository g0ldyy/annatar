import asyncio

import aiohttp
import structlog

from annatar.debrid.rd_models import InstantFile, TorrentInfo, UnrestrictedLink
from annatar.logging import timestamped
from annatar.torrent import Torrent

ROOT_URL = "https://api.real-debrid.com/rest/1.0"


log = structlog.get_logger(__name__)


@timestamped()
async def add_magnet(magnet_link: str, debrid_token: str) -> str | None:
    """
    Adds a magnet link to RD and returns the torrent id.
    """
    api_url = f"{ROOT_URL}/torrents/addMagnet"
    body = {"magnet": magnet_link}

    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.post(api_url, headers=api_headers, data=body) as response:
            if response.status not in range(200, 300):
                log.error(
                    "Got status adding magnet to RD", status=response.status, magnet=magnet_link
                )
                return None
            response_json = await response.json()
            log.info("Magnet added to RD", torrent=response_json["id"], magnet=magnet_link)
            return response_json["id"]


@timestamped()
async def get_instant_availability(info_hash: str, debrid_token: str) -> list[InstantFile]:
    api_url = f"{ROOT_URL}/torrents/instantAvailability/{info_hash}"
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.get(api_url, headers=api_headers) as response:
            if response.status not in range(200, 300):
                log.error(
                    "Error getting instant availability",
                    status=response.status,
                    reason=response.reason,
                    body=await response.text(),
                )
                return []
            res = await response.json()

    cached_files: list[InstantFile] = [
        InstantFile(id=int(id_key), **file_info)
        for value in res.values()
        if value
        for item in value.get("rd", [])
        for id_key, file_info in item.items()
    ]
    log.info("found cached files", count=len(cached_files))
    return cached_files


@timestamped()
async def list_torrents(debrid_token: str) -> list[TorrentInfo]:
    api_url = f"{ROOT_URL}/torrents"
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.get(api_url, headers=api_headers) as response:
            if response.status not in range(200, 300):
                log.error(
                    "Error getting torrent list",
                    status=response.status,
                    reason=response.reason,
                    body=await response.text(),
                )
                return []
            response_json = await response.json()
    return [TorrentInfo(**t) for t in response_json]


@timestamped()
async def get_torrent_info(
    torrent_id: str,
    debrid_token: str,
) -> TorrentInfo | None:
    api_url = f"{ROOT_URL}/torrents/info/{torrent_id}"
    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.get(api_url, headers=api_headers) as response:
            if response.status not in range(200, 300):
                log.error(
                    "Error getting torrent info",
                    status=response.status,
                    reason=response.reason,
                    body=await response.text(),
                )
                return None
            response_json = await response.json()
            torrent_info: TorrentInfo = TorrentInfo(**response_json)
            return torrent_info


@timestamped()
async def select_torrent_file(
    torrent_id: str,
    file_id: str,
    debrid_token: str,
    season_episode: list[int] = [],
) -> bool:
    async with aiohttp.ClientSession() as session:
        for i in range(1, 5):
            api_headers = {"Authorization": f"Bearer {debrid_token}"}
            async with session.post(
                f"{ROOT_URL}/torrents/selectFiles/{torrent_id}",
                headers=api_headers,
                data={"files": file_id},
            ) as response:
                if response.status not in range(200, 300):
                    log.error(
                        "Error selecting torrent file",
                        status=response.status,
                        reason=response.reason,
                        body=await response.text(),
                        attempt=i,
                    )
                    await asyncio.sleep(i)
                return True
    log.error("failed to select torrent file", torrent_id=torrent_id, file_id=file_id, attempts=5)
    return False


@timestamped()
async def unrestrict_link(
    torrent: Torrent,
    link: str,
    debrid_token: str,
) -> UnrestrictedLink | None:
    api_url = f"{ROOT_URL}/unrestrict/link"
    body = {"link": link}

    async with aiohttp.ClientSession() as session:
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.post(api_url, headers=api_headers, data=body) as response:
            if response.status not in range(200, 300):
                log.error(
                    "Error getting unrestrict link",
                    status=response.status,
                    reason=response.reason,
                    body=await response.text(),
                )
                return None
            unrestrict_response_json = await response.json()
            unrestrict_response_json["torrent"] = torrent
            unrestrict_info: UnrestrictedLink = UnrestrictedLink(**unrestrict_response_json)
            log.info("Got unrestrict link", link=unrestrict_info.link, info_hash=torrent.info_hash)
            return unrestrict_info


@timestamped()
async def delete_torrent(torrent_id: str, debrid_token: str):
    async with aiohttp.ClientSession() as session:
        api_url = f"{ROOT_URL}/torrents/delete/{torrent_id}"
        api_headers = {"Authorization": f"Bearer {debrid_token}"}
        async with session.delete(api_url, headers=api_headers) as response:
            if response.status not in range(200, 300):
                log.error(
                    "Error deleting torrent",
                    status=response.status,
                    reason=response.reason,
                    body=await response.text(),
                )
                return
