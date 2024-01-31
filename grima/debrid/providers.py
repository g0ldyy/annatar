from abc import ABC, abstractmethod

from grima.debrid import pm, rd
from grima.debrid.models import StreamLink
from grima.torrent import Torrent


class DebridService(ABC):
    @abstractmethod
    async def get_stream_links(
        self,
        torrents: list[Torrent],
        debrid_token: str,
        season_episode: list[int],
        max_results: int = 5,
    ) -> list[StreamLink]:
        return []


class RealDebridProvider(DebridService):
    async def get_stream_links(
        self,
        torrents: list[Torrent],
        debrid_token: str,
        season_episode: list[int],
        max_results: int = 5,
    ) -> list[StreamLink]:
        return await rd.get_stream_links(
            torrents=torrents,
            debrid_token=debrid_token,
            season_episode=season_episode,
            max_results=max_results,
        )


class PremiumizeProvider(DebridService):
    async def get_stream_links(
        self,
        torrents: list[Torrent],
        debrid_token: str,
        season_episode: list[int],
        max_results: int = 5,
    ) -> list[StreamLink]:
        return await pm.get_stream_links(
            torrents=torrents,
            debrid_token=debrid_token,
            season_episode=season_episode,
            max_results=max_results,
        )


def get_provider(provider_name: str) -> DebridService:
    if provider_name == "real-debrid":
        return RealDebridProvider()
    if provider_name == "premiumize":
        return PremiumizeProvider()
    return RealDebridProvider()
