import os
from abc import ABC, abstractmethod
from typing import Optional

import redis.asyncio as redis
import structlog

log = structlog.get_logger(__name__)


class Cache(ABC):
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def set(self, key: str, value: str, ttl_seconds: int) -> bool:
        log.debug("SET cache", cacher=self.name(), key=key)
        pass

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        log.debug("GET cache", cacher=self.name(), key=key)
        pass


class NoCache(Cache):
    async def set(self, key: str, value: str, ttl_seconds: int) -> bool:
        return True

    async def get(self, key: str) -> Optional[str]:
        return None


class RedisCache(Cache):
    url: str
    pool: redis.ConnectionPool

    @staticmethod
    def from_env() -> Optional["RedisCache"]:
        if "REDIS_URL" in os.environ:
            return RedisCache(
                url=os.environ.get("REDIS_URL", ""),
            )
        return None

    def __init__(self, url: str):
        self.url = url
        self.pool = redis.ConnectionPool.from_url(  # type: ignore
            url=url,
            decode_responses=True,
            max_connections=20,
        )

    async def ping(self) -> bool:
        client = redis.Redis.from_pool(self.pool)
        res = await client.ping()  # type: ignore
        await client.aclose()
        return res  # type: ignore

    async def set(self, key: str, value: str, ttl_seconds: int = 60 * 60) -> bool:
        client: redis.Redis = redis.Redis.from_pool(self.pool)
        try:
            return await client.set(key, value, ex=ttl_seconds)  # type: ignore
        finally:
            await client.aclose()

    async def get(self, key: str) -> Optional[str]:
        client: redis.Redis = redis.Redis.from_pool(self.pool)
        try:
            res: Optional[str] = await client.get(key)  # type: ignore
            if res is None:
                return None
            return str(res)  # type: ignore
        finally:
            await client.aclose()


CACHE: Cache = RedisCache.from_env() or NoCache()
log.info("using cache", cache=CACHE.name())
