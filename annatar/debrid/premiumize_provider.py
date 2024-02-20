import asyncio
from typing import AsyncGenerator

from annatar.debrid import pm
from annatar.debrid.debrid_service import DebridService
from annatar.debrid.models import StreamLink


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
        torrents: list[str],
        season_episode: list[int],
        stop: asyncio.Event,
        max_results: int,
    ) -> AsyncGenerator[StreamLink, None]:
        async for sl in pm.get_stream_links(
            torrents=torrents,
            debrid_token=self.api_key,
            season_episode=season_episode,
            stop=stop,
            max_results=max_results,
        ):
            yield sl
