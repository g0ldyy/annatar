from abc import ABC, abstractmethod
from typing import AsyncGenerator

from annatar.debrid.models import StreamLink
from annatar.torrent import Torrent


class DebridService(ABC):
    api_key: str

    def __str__(self) -> str:
        return self.name()

    def __init__(self, api_key: str):
        self.api_key = api_key

    @abstractmethod
    def shared_cache(self) -> bool:
        pass

    @abstractmethod
    def short_name(self) -> str:
        pass

    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def id(self) -> str:
        pass

    @abstractmethod
    async def get_stream_links(
        self,
        torrents: AsyncGenerator[Torrent, None],
        season_episode: list[int],
        max_results: int = 5,
    ) -> AsyncGenerator[StreamLink, None]:
        pass
