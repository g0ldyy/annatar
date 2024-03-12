import asyncio
from datetime import timedelta
from typing import Any, AsyncGenerator

import aiohttp
import structlog
from pydantic import TypeAdapter

from annatar.database import db
from annatar.debrid import magnet
from annatar.debrid.debrid_service import DebridService
from annatar.debrid.models import StreamLink
from annatar.debrid.offcloud_models import (
    AddMagnetResponse,
    CacheResponse,
    CloudHistoryItem,
    CloudStatusResponse,
    TorrentInfo,
)
from annatar.human import is_video
from annatar.torrent import TorrentMeta

log = structlog.get_logger(__name__)


class OffCloudProvider(DebridService):
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

        log.debug("make request", method=method, url=url, data=data, params=params)
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

        return CloudStatusResponse.model_validate(response)

    async def get_torrent_instant_availability(
        self, magnet_links: list[str]
    ) -> CacheResponse | None:
        response = await self.make_request("POST", "/cache", data={"hashes": magnet_links})
        if not response:
            return None
        return CacheResponse(**response)

    async def get_available_torrent(self, info_hash: str) -> CloudHistoryItem | None:
        available_torrents = await self.get_user_torrent_list()
        info_hash = info_hash.casefold()
        if not available_torrents:
            return None
        for torrent in available_torrents:
            if torrent.original_link and info_hash in torrent.original_link.casefold():
                return torrent
        return None

    async def explore_folder_links(self, request_id: str) -> list[str] | None:
        response = await self.make_request("GET", f"/cloud/explore/{request_id}")
        if not response:
            return None

        return TypeAdapter(list[str]).validate_python(response)

    async def create_download_link(
        self,
        request_id: str,
        torrent_info: TorrentInfo,
        season: int = 0,
        episode: int = 0,
    ) -> str | None:
        if not torrent_info.is_directory:
            return f"https://{torrent_info.server}.offcloud.com/cloud/download/{request_id}/{torrent_info.file_name}"

        response = await self.explore_folder_links(request_id)
        if not response:
            return None
        for link in response:
            if not is_video(link, torrent_info.file_size):
                continue

            if not season and not episode:
                return link

            if season and episode:
                meta = TorrentMeta.parse_title(link.split("/")[-1])
                if season in meta.season and episode in meta.episode:
                    return link
        return None

    async def get_stream_link(
        self,
        info_hash: str,
        season: int,
        episode: int,
    ) -> StreamLink | None:
        cache_key = f"offcloud:{info_hash}:files"
        if cached_files_raw := await db.get(cache_key):
            cached_files = TypeAdapter(list[StreamLink]).validate_python(cached_files_raw)
            for file in cached_files:
                meta = TorrentMeta.parse_title(file.name)
                if not season:
                    return file
                if season in meta.season and episode in meta.episode:
                    return file
            return None

        # check it live
        magnet_resp = await self.add_magent_link(magnet.make_magnet_link(info_hash))
        if not magnet_resp:
            return None

        torrent_infos = await self.get_torrent_info(magnet_resp.request_id)
        if not torrent_infos:
            log.error("failed to get torrent info", magnet_resp=magnet_resp)
            return None

        torrent_info = next(
            (r for r in torrent_infos.requests if r.request_id == magnet_resp.request_id), None
        )
        if not torrent_info:
            log.error("failed to find torrent info", magnet_resp=magnet_resp)
            return None

        download_link = await self.create_download_link(
            magnet_resp.request_id,
            torrent_info,
            season,
            episode,
        )
        if not download_link:
            log.debug("failed to create download link", magnet_resp=magnet_resp)
            return None
        return StreamLink(
            url=download_link,
            name=torrent_info.file_name,
            size=torrent_info.file_size,
        )

    # implement DebridService
    def shared_cache(self) -> bool:
        return False

    def short_name(self) -> str:
        return "OC"

    def name(self) -> str:
        return "OffCloud"

    def id(self) -> str:
        return "offcloud"

    async def get_stream_links(
        self,
        torrents: list[str],
        stop: asyncio.Event,
        max_results: int,
        season: int = 0,
        episode: int = 0,
    ) -> AsyncGenerator[StreamLink, None]:
        available_torrents = await self.get_torrent_instant_availability(torrents)
        if not available_torrents or len(available_torrents.cached_items) == 0:
            log.debug("no available torrents")
            return

        i = 0
        for torrent in available_torrents.cached_items:
            if not torrent:
                continue
            if link := await self.get_stream_link(
                info_hash=torrent, season=season, episode=episode
            ):
                yield link
                i += 1
                if i >= max_results:
                    return
            if stop.is_set():
                return


async def get_file_size(info_hash: str, link: str) -> int | None:
    cache_key = f"offcloud:v1:{info_hash}:{link}:size"
    if size := await db.get(cache_key):
        await db.set_ttl(cache_key, timedelta(days=30))
        return int(size)

    async with aiohttp.ClientSession() as session, session.head(
        link, max_redirects=False
    ) as response:
        response.raise_for_status()
        size = int(response.headers.get("Content-Length") or 0) or None

    if size:
        await db.set(cache_key, str(size), ttl=timedelta(days=30))

    return size
