from typing import Any, AsyncGenerator, TypeVar

import structlog
from pydantic import BaseModel, field_validator

from annatar.pubsub import pubsub
from annatar.pubsub.pubsub import Topic
from annatar.torrent import Category

log = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class TorrentSearchCriteria(BaseModel):
    imdb: str
    year: int
    query: str
    season: int
    episode: int
    category: Category


class TorrentSearchResult(BaseModel):
    search_criteria: TorrentSearchCriteria
    category: list[int] = []
    info_hash: str
    title: str
    guid: str
    imdb: str = ""
    magnet_link: str = ""
    tracker: str = ""
    Size: int = 0
    languages: list[str] = []
    subs: list[str] = []
    year: int = 0
    seeders: int = 0

    @field_validator("info_hash", mode="before")
    @classmethod
    def consistent_info_hash(cls: Any, v: Any):
        if v is None:
            return None
        if isinstance(v, str):
            # info_hash needs to be upper case for comparison
            return v.upper()
        return v

    @staticmethod
    async def listen() -> AsyncGenerator["TorrentSearchResult", None]:
        async for item in pubsub.consume_topic(
            topic=Topic.TorrentSearchResult,
            model=TorrentSearchResult,
        ):
            yield item

    @staticmethod
    async def publish(result: "TorrentSearchResult") -> int:
        return await pubsub.publish(Topic.TorrentSearchResult, result.model_dump_json())


class TorrentAdded(BaseModel):
    info_hash: str
    title: str
    imdb: str
    season: int | None = None
    episode: int | None = None

    @staticmethod
    async def listen() -> AsyncGenerator["TorrentAdded", None]:
        async for item in pubsub.consume_topic(
            topic=Topic.TorrentAdded,
            model=TorrentAdded,
        ):
            yield item

    @staticmethod
    async def publish(result: "TorrentAdded") -> int:
        return await pubsub.publish(Topic.TorrentAdded, result.model_dump_json())
