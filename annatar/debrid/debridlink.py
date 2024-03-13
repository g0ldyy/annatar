import asyncio
import urllib.parse
from typing import Any, AsyncGenerator

import aiohttp
import structlog
from pydantic import BaseModel

from annatar import human, magnet
from annatar.debrid.debrid_service import DebridService, StreamLink
from annatar.debrid.debridlink_models import (
    CachedFile,
    CachedMagnet,
    CachedResponse,
    TorrentInfo,
)
from annatar.torrent import TorrentMeta

log = structlog.get_logger(__name__)


class HttpResponse(BaseModel):
    status: int
    headers: list[tuple[str, str]]
    response_json: dict[str, Any] | None = None
    response_text: str | None = None


class DebridLink(DebridService):
    BASE_URL = "https://debrid-link.com/api/v2"

    async def make_request(
        self,
        method: str,
        url: str,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> HttpResponse | None:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session, session.request(
            method, f"{self.BASE_URL}{url}", params=query, json=body, headers=headers
        ) as response:
            response.raise_for_status()
            return HttpResponse(
                status=response.status,
                headers=list(response.headers.items()),
                response_json=await response.json(),
                response_text=await response.text(),
            )

    async def get_cached_torrents(self, info_hashes: list[str]) -> dict[str, CachedMagnet] | None:
        magnet_links = [urllib.parse.quote_plus(magnet.make_magnet_link(x)) for x in info_hashes]
        response = await self.make_request(
            method="GET",
            url="/seedbox/cached",
            query={"url": ",".join(magnet_links)},
        )
        if response is None:
            return None
        resp = CachedResponse.model_validate(response.response_json)
        if not resp.success:
            log.info("failed to get cached torrents", response=resp)
            return None
        return resp.value

    async def get_stream_for_torrent(
        self,
        info_hash: str,
        file_name: str,
    ) -> StreamLink | None:
        torrent_info = await self.get_torrent_info(info_hash)
        if torrent_info:
            log.debug("torrent already exists", info_hash=info_hash)
        else:
            log.debug("adding torrent", info_hash=info_hash)
            torrent_info = await self.add_torrent(info_hash)

        if torrent_info is None:
            log.error("failed to add torrent", info_hash=info_hash)
            return None
        for file in torrent_info.files:
            if file.name == file_name:
                return StreamLink(
                    url=file.download_url,
                    name=file.name,
                    size=file.size,
                )
        log.error("no matching file", info_hash=info_hash, file_name=file_name)
        return None

    async def add_torrent(self, info_hash: str) -> TorrentInfo | None:
        raw_resp = await self.make_request(
            "POST", "/seedbox/add", body={"url": magnet.make_magnet_link(info_hash)}
        )
        if raw_resp is None or raw_resp.response_json is None:
            return None
        if doc := raw_resp.response_json.get("value"):
            return TorrentInfo.model_validate(doc)
        return None

    async def get_torrent_info(self, torrent_id: str) -> TorrentInfo | None:
        raw_resp = await self.make_request("GET", "/seedbox/list", query={"ids": torrent_id})
        if raw_resp is None or raw_resp.response_json is None:
            return None
        if items := raw_resp.response_json.get("value", []):
            for item in items:
                if item.get("id") == torrent_id:
                    return TorrentInfo.model_validate(item)
        return None

    # implements DebridService
    def shared_cache(self) -> bool:
        # TODO: Figure out if this is true
        return False

    def short_name(self) -> str:
        return "DL"

    def name(self) -> str:
        return "Debrid Link"

    def id(self) -> str:
        return "debridlink"

    async def get_stream_links(
        self,
        torrents: list[str],
        stop: asyncio.Event,
        max_results: int,
        season: int = 0,
        episode: int = 0,
    ) -> AsyncGenerator[StreamLink, None]:
        cached_torrents = await self.get_cached_torrents(torrents)
        if cached_torrents is None:
            return

        i = 0
        for magnet_link, torrent in cached_torrents.items():
            info_hash = magnet.parse_magnet_link(magnet_link)
            if stop.is_set():
                break
            matched_file = get_matched_file(torrent.files, season, episode)
            if not matched_file:
                log.debug("no matching file", info_hash=info_hash, season=season, episode=episode)
                continue
            yield StreamLink(
                url=f"/dl/{self.api_key}/{info_hash}/{matched_file.name}",
                name=matched_file.name,
                size=matched_file.size,
            )
            i += 1
            if i >= max_results:
                break


def get_matched_file(files: list[CachedFile], season: int, episode: int) -> CachedFile | None:
    if not files:
        return None

    by_size: list[CachedFile] = [
        f
        for f in sorted(files, key=lambda x: x.size, reverse=True)
        if human.is_video(f.name, f.size)
    ]
    if not by_size:
        return None

    for file in by_size:
        meta = TorrentMeta.parse_title(file.name)
        if meta.is_trash():
            log.debug("skipping trash file", file=file.name)
            continue
        if season == 0 and episode == 0:
            log.debug("no season/episode specified, using first file", file=file.name)
            return file
        if meta.is_season_episode(season, episode):
            log.debug("matched season/episode", file=file.name, season=season, episode=episode)
            return file

    log.debug("no matching season/episode", season=season, episode=episode)
    return None
