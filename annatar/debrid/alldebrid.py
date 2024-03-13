import asyncio
import urllib.parse
from typing import Any, AsyncGenerator

import aiohttp
import structlog
from pydantic import BaseModel

from annatar import human
from annatar.debrid.alldebrid_models import (
    AddTorrentResponse,
    CachedFile,
    CachedMagnet,
    CachedResponse,
    MagnetStatusResponse,
    TorrentInfo,
    UnlockLink,
)
from annatar.debrid.debrid_service import DebridService, StreamLink
from annatar.torrent import TorrentMeta

log = structlog.get_logger(__name__)


class HttpResponse(BaseModel):
    status: int
    headers: list[tuple[str, str]]
    response_json: dict[str, Any] | None = None
    response_text: str | None = None


class AllDebridProvider(DebridService):
    BASE_URL = "https://api.alldebrid.com/v4"

    async def make_request(
        self,
        method: str,
        url: str,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        form: aiohttp.FormData | None = None,
    ) -> HttpResponse | None:
        query = query or {}
        query["agent"] = "https://gitlab.com/stremio-add-ons/annatar"
        log.debug("making request", method=method, url=url, query=query, body=body, form=form)
        query["apikey"] = self.api_key
        async with aiohttp.ClientSession() as session, session.request(
            method,
            f"{self.BASE_URL}{url}",
            params=query,
            json=body,
            data=form,
        ) as response:
            response.raise_for_status()
            return HttpResponse(
                status=response.status,
                headers=list(response.headers.items()),
                response_json=await response.json(),
                response_text=await response.text(),
            )

    async def get_cached_torrents(self, info_hashes: list[str]) -> list[CachedMagnet]:
        form = aiohttp.FormData(quote_fields=False)
        for info_hash in info_hashes:
            form.add_field("magnets[]", info_hash)

        log.debug("getting cached torrents", info_hashes=form._fields)
        response = await self.make_request(
            method="POST",
            url="/magnet/instant",
            form=form,
        )
        if response is None:
            log.info("no response from alldebrid")
            return []
        resp = CachedResponse.model_validate(response.response_json)
        if not resp:
            log.info("no cached torrents", response=response)
            return []
        if resp.status != "success":
            log.info("failed to get cached torrents", error=resp.error, status=resp.status)
            return []
        return [m for m in resp.magnets if m.instant]

    async def get_or_add_torrent(self, info_hash: str) -> TorrentInfo | None:
        torrent_infos: MagnetStatusResponse | None = await self.get_torrent_info()
        if torrent_infos and torrent_infos.magnets:
            for torrent in torrent_infos.magnets:
                if torrent.hash.casefold() == info_hash.casefold():
                    return torrent

        log.debug("torrent not found, adding", info_hash=info_hash)
        torrent_added = await self.add_torrent(info_hash)
        if torrent_added and torrent_added.magnets:
            log.info("added torrent", info_hash=info_hash, added=torrent_added)
            torrent_infos = await self.get_torrent_info(torrent_added.magnets[0].id)
            if not torrent_infos:
                log.debug("failed to get torrent info", info_hash=info_hash)
                return None
            for torrent in torrent_infos.magnets:
                if torrent.hash.casefold() == info_hash.casefold():
                    return torrent
        return None

    async def get_stream_for_torrent(
        self,
        info_hash: str,
        file_name: str,
    ) -> StreamLink | None:
        torrent_info: TorrentInfo | None = await self.get_or_add_torrent(info_hash)
        if not torrent_info:
            log.info("failed to get torrent info", info_hash=info_hash)
            return None

        for file in torrent_info.links:
            if file.filename != file_name:
                continue
            link = await self.unlock_link(file.link)
            if not link:
                log.info("failed to unlock link", file=file)
                continue
            return StreamLink(
                url=link.link,
                name=link.filename,
                size=link.filesize,
            )
        return None

    async def unlock_link(self, link: str) -> UnlockLink | None:
        response = await self.make_request("GET", "/link/unlock", query={"link": link})
        if response is None or response.response_json is None:
            return None
        if response.response_json.get("status", "") != "success":
            log.info("failed to unlock link", link=link, response=response.response_json)
            return None
        return UnlockLink.model_validate(response.response_json.get("data", {}))

    async def get_torrent_info(self, torrent_id: int | None = None) -> MagnetStatusResponse | None:
        q = {"id": torrent_id} if torrent_id else None
        response = await self.make_request("GET", "/magnet/status", query=q)
        if response is None:
            return None
        return MagnetStatusResponse.model_validate(response.response_json)

    async def add_torrent(self, info_hash: str) -> AddTorrentResponse | None:
        raw_resp = await self.make_request(
            "POST", "/magnet/upload", form=aiohttp.FormData({"magnet[]": info_hash})
        )
        if raw_resp is None or raw_resp.response_json is None:
            return None
        return AddTorrentResponse.model_validate(raw_resp.response_json)

    # implements DebridService
    def shared_cache(self) -> bool:
        # TODO: Figure out if this is true
        return False

    def short_name(self) -> str:
        return "AD"

    def name(self) -> str:
        return "AllDebrid"

    def id(self) -> str:
        return "alldebrid"

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

        log.debug("got cached torrents", count=len(cached_torrents))

        i = 0
        for torrent in cached_torrents:
            if stop.is_set():
                break
            log.debug("getting stream links", info_hash=torrent.hash)
            matched_file = get_matched_file(torrent.files, season, episode)
            if not matched_file:
                log.debug(
                    "no matching file", info_hash=torrent.hash, season=season, episode=episode
                )
                continue
            filename = urllib.parse.quote(matched_file.name)
            yield StreamLink(
                url=f"/ad/{self.api_key}/{torrent.hash}/{filename}",
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
