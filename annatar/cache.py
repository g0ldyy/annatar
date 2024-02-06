import os
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Optional, Type, TypeVar

import redis.asyncio as redis
import structlog
from pydantic import BaseModel, ValidationError

from annatar.logging import timestamped

log = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class Cache(ABC):
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def set(self, key: str, value: str, ttl: timedelta) -> bool:
        log.debug("SET cache", cacher=self.name(), key=key)
        pass

    @abstractmethod
    async def set_model(self, key: str, model: BaseModel, ttl: timedelta) -> bool:
        pass

    @abstractmethod
    async def get_model(self, key: str, model: Type[T]) -> Optional[T]:
        pass

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        log.debug("GET cache", cacher=self.name(), key=key)
        pass

    @abstractmethod
    async def ping(self) -> bool:
        pass


class NoCache(Cache):
    async def set(self, key: str, value: str, ttl: timedelta) -> bool:
        return True

    async def get(self, key: str) -> Optional[str]:
        return None

    async def set_model(self, key: str, model: BaseModel, ttl: timedelta) -> bool:
        return True

    async def get_model(self, key: str, model: Type[T]) -> Optional[T]:
        return None

    async def ping(self) -> bool:
        return True


class RedisCache(Cache):
    url: str
    pool: redis.ConnectionPool

    @staticmethod
    def from_env() -> Optional["RedisCache"]:
        redis_url: Optional[str] = os.environ.get("REDIS_URL")
        if redis_url:
            return RedisCache(
                url=os.environ.get("REDIS_URL", ""),
            )
        return None

    def __init__(self, url: str):
        self.url = url
        self.pool: redis.ConnectionPool = redis.ConnectionPool.from_url(  # type: ignore
            url=url,
            decode_responses=True,
            max_connections=20,
        )

    async def ping(self) -> bool:
        client = redis.Redis.from_pool(self.pool)  # type: ignore
        res: Optional[str] = await client.ping()  # type: ignore
        await client.aclose()  # type: ignore
        return True if res == "PONG" else False

    async def get_model(self, key: str, model: Type[T]) -> Optional[T]:
        res: Optional[str] = await self.get(key)
        if res is None:
            return None
        try:
            return model.model_validate_json(res)
        except ValidationError as e:
            log.error(
                "failed to validate model", key=key, model=model.__name__, json=res, error=str(e)
            )
            return None

    async def set_model(self, key: str, model: BaseModel, ttl: timedelta) -> bool:
        return await self.set(key, model.model_dump_json(), ttl=ttl)

    @timestamped(["key"])
    async def set(self, key: str, value: str, ttl: timedelta) -> bool:
        client: redis.Redis = redis.Redis.from_pool(self.pool)  # type: ignore
        try:
            return await client.set(key, value, ex=int(ttl.total_seconds()))  # type: ignore
            await client.aclose()
        except Exception as e:
            log.error("failed to set cache", key=key, error=str(e))
            return False

    @timestamped(["key"])
    async def get(self, key: str) -> Optional[str]:
        client: redis.Redis = redis.Redis.from_pool(self.pool)  # type: ignore
        try:
            res: Optional[str] = await client.get(key)  # type: ignore
            if res is None:
                log.debug("cache miss", key=key)
                return None
            log.debug("cache hit", key=key)
            return str(res)  # type: ignore
        except Exception as e:
            log.error("failed to get cache", key=key, error=str(e))
            return None


CACHE: Cache = RedisCache.from_env() or NoCache()
log.info("using cache", cache=CACHE.name())
