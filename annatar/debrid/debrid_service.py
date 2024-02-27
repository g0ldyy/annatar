import asyncio
from abc import ABC, abstractmethod
from typing import AsyncGenerator

from annatar.debrid.models import StreamLink


class DebridService(ABC):
    api_key: str

    def __str__(self) -> str:
        return self.name()

    def __init__(self, api_key: str, source_ip: str):
        self.api_key = api_key
        self.source_ip = source_ip

    @abstractmethod
    def shared_cache(self) -> bool:
        ...

    @abstractmethod
    def short_name(self) -> str:
        ...

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def id(self) -> str:
        ...

    @abstractmethod
    async def get_stream_links(
        self,
        torrents: list[str],
        season_episode: list[int],
        stop: asyncio.Event,
        max_results: int,
    ) -> AsyncGenerator[StreamLink, None]:
        ...
