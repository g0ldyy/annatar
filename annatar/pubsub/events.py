import asyncio
from typing import Any, TypeVar

import structlog
from pydantic import BaseModel, field_validator

from annatar.pubsub import pubsub
from annatar.pubsub.pubsub import Topic
from annatar.torrent import Category

log = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class SearchRequest(BaseModel):
    imdb: str
    category: Category
    season: int | None = None
    episode: int | None = None

    @staticmethod
    async def listen(queue: asyncio.Queue["SearchRequest"], consumer: str):
        await pubsub.consume_topic(
            topic=Topic.SearchRequest,
            model=SearchRequest,
            queue=queue,
            consumer=consumer,
        )

    @staticmethod
    async def publish(request: "SearchRequest") -> int:
        return await pubsub.publish(Topic.SearchRequest, request.model_dump_json())


class TorrentSearchCriteria(BaseModel):
    imdb: str
    query: str
    category: Category
    year: int = 0


class TorrentSearchResult(BaseModel):
    search_criteria: TorrentSearchCriteria
    category: list[int] = []
    info_hash: str = ""
    title: str
    guid: str
    indexer: str = ""
    imdb: str = ""
    magnet_link: str = ""
    tracker: str = ""
    size: int = 0
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
    async def listen(queue: asyncio.Queue["TorrentSearchResult"], consumer: str):
        await pubsub.consume_topic(
            topic=Topic.TorrentSearchResult,
            model=TorrentSearchResult,
            queue=queue,
            consumer=consumer,
        )

    @staticmethod
    async def publish(result: "TorrentSearchResult") -> int:
        return await pubsub.publish(Topic.TorrentSearchResult, result.model_dump_json())


class TorrentAdded(BaseModel):
    info_hash: str
    title: str
    imdb: str
    size: int
    indexer: str
    category: str
    season: int | None = None
    episode: int | None = None

    @staticmethod
    async def listen(queue: asyncio.Queue["TorrentAdded"], consumer: str):
        await pubsub.consume_topic(
            topic=Topic.TorrentAdded,
            model=TorrentAdded,
            queue=queue,
            consumer=consumer,
        )

    @staticmethod
    async def publish(result: "TorrentAdded") -> int:
        return await pubsub.publish(Topic.TorrentAdded, result.model_dump_json())
