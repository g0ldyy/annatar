from abc import ABC, abstractmethod
from typing import Optional

from annatar.debrid.models import StreamLink
from annatar.torrent import Torrent

_providers: list["DebridService"] = []


def register_provider(prov: "DebridService"):
    _providers.append(prov)


class DebridService(ABC):
    api_key: str

    def __str__(self) -> str:
        return self.__class__.__name__

    def __init__(self, api_key: str):
        self.api_key = api_key

    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def id(self) -> str:
        pass

    @abstractmethod
    async def get_stream_links(
        self,
        torrents: list[Torrent],
        season_episode: list[int],
        max_results: int = 5,
    ) -> list[StreamLink]:
        return []


def list_providers() -> list[dict[str, str]]:
    return [{"id": p.id(), "name": p.name()} for p in _providers]


def get_provider(provider_name: str, api_key: str) -> Optional[DebridService]:
    for p in _providers:
        if p.name() == provider_name:
            return p.__class__(api_key)
    return None
