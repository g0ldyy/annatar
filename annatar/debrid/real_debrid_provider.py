from typing import Optional

from annatar.debrid import rd
from annatar.debrid.debrid_service import DebridService
from annatar.debrid.models import StreamLink
from annatar.torrent import Torrent


class RealDebridProvider(DebridService):
    def __str__(self) -> str:
        return "RealDebridProvider"

    def short_name(self) -> str:
        return "RD"

    def name(self) -> str:
        return "real-debrid.com"

    def id(self) -> str:
        return "real_debrid"

    def shared_cache(self):
        return True

    async def get_stream_links(
        self,
        torrents: list[Torrent],
        season_episode: list[int],
        max_results: int = 5,
    ) -> list[StreamLink]:
        return await rd.get_stream_links(
            torrents=torrents,
            debrid_token=self.api_key,
            season_episode=season_episode,
            max_results=max_results,
        )

    async def get_stream_for_torrent(
        self,
        info_hash: str,
        file_id: str,
        debrid_token: str,
    ) -> Optional[StreamLink]:
        return await rd.get_stream_for_torrent(
            info_hash=info_hash,
            file_id=file_id,
            debrid_token=debrid_token,
        )
