from typing import Any

import aiohttp
import structlog
from pydantic import TypeAdapter

from annatar.debrid.debrid_service import DebridService
from annatar.debrid.offcloud_models import (
    AddMagnetResponse,
    CacheResponse,
    CloudHistoryItem,
    CloudStatusResponse,
    TorrentInfo,
)
from annatar.human import is_video

log = structlog.get_logger(__name__)


class OffCloud(DebridService):
    BASE_URL = "https://offcloud.com/api"

    async def make_request(
        self,
        method: str,
        url: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        params = params or {}
        params["key"] = self.api_key
        url = self.BASE_URL + url

        async with aiohttp.ClientSession() as session, session.request(
            method,
            url,
            data=data,
            params=params,
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def add_magent_link(self, magnet_link: str) -> AddMagnetResponse | None:
        response_data = await self.make_request("POST", "/cloud", data={"url": magnet_link})
        if not response_data:
            return None

        if "requestId" not in response_data:
            if "not_available" in response_data:
                return None
            log.error("failed to add magnet to offcloud", response=response_data)
            return None
        return AddMagnetResponse(**response_data)

    async def get_user_torrent_list(self) -> list[CloudHistoryItem] | None:
        response = await self.make_request("GET", "/cloud/history")
        if not response:
            return None
        return TypeAdapter(list[CloudHistoryItem]).validate_python(response)

    async def get_torrent_info(self, request_id: str) -> CloudStatusResponse | None:
        response = await self.make_request(
            "POST", "/cloud/status", data={"requestIds": [request_id]}
        )
        if not response:
            return None

        return CloudStatusResponse(**response)

    async def get_torrent_instant_availability(
        self, magnet_links: list[str]
    ) -> CacheResponse | None:
        response = await self.make_request("POST", "/cache", data={"hashes": magnet_links})
        if not response:
            return None
        return CacheResponse(**response)

    async def get_available_torrent(self, info_hash: str) -> CloudHistoryItem | None:
        available_torrents = await self.get_user_torrent_list()
        if not available_torrents:
            return None
        for torrent in available_torrents:
            if torrent.original_link and info_hash in torrent.original_link:
                return torrent
        return None

    async def explore_folder_links(self, request_id: str) -> list[str] | None:
        response = await self.make_request("GET", f"/cloud/explore/{request_id}")
        if not response:
            return None

        return TypeAdapter(list[str]).validate_python(response)

    async def create_download_link(self, request_id: str, torrent_info: TorrentInfo, filename: str):
        if not torrent_info.is_directory:
            return f"https://{torrent_info.server}.offcloud.com/cloud/download/{request_id}/{torrent_info.file_name}"

        response = await self.explore_folder_links(request_id)
        if not response:
            return None
        for link in response:
            if filename is None and is_video(link):
                return link
            if filename is not None and filename in link:
                return link
        return None
