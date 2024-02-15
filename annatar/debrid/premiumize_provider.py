from annatar.debrid import pm
from annatar.debrid.debrid_service import DebridService
from annatar.debrid.models import StreamLink
from annatar.torrent import Torrent


class PremiumizeProvider(DebridService):
    def __str__(self) -> str:
        return "PremiumizeProvider"

    def short_name(self) -> str:
        return "PM"

    def name(self) -> str:
        return "premiumize.me"

    def id(self) -> str:
        return "premiumize"

    def shared_cache(self):
        return False

    async def get_stream_links(
        self,
        torrents: list[Torrent],
        season_episode: list[int],
        max_results: int = 5,
    ) -> list[StreamLink]:
        return await pm.get_stream_links(
            torrents=torrents,
            debrid_token=self.api_key,
            season_episode=season_episode,
            max_results=max_results,
        )
