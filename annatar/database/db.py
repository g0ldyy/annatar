import asyncio
import os
from datetime import timedelta
from typing import Optional, Type, TypeVar

import structlog
from prometheus_client import Histogram
from pydantic import BaseModel, ValidationError
from redislite import StrictRedis  # type: ignore

from annatar import instrumentation

log = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

DB_PATH = os.environ.get("DB_PATH", "annatar.db")
REDIS_URL = os.environ.get("REDIS_URL", "")
REDIS_FLAGS = {"socket_timeout": 3.0, "socket_connect_timeout": 3.0}
redis: StrictRedis = (
    StrictRedis(host=REDIS_URL, **REDIS_FLAGS) if REDIS_URL else StrictRedis(DB_PATH, **REDIS_FLAGS)
)

REQUEST_DURATION = Histogram(
    name="redis_command_duration_seconds",
    documentation="Duration of Redis requests in seconds",
    labelnames=["command"],
    registry=instrumentation.registry(),
)


@REQUEST_DURATION.labels("PING").time()
async def ping() -> bool:
    redis.ping()
    return True


async def get_model(key: str, model: Type[T], force: bool = False) -> Optional[T]:
    res: Optional[str] = await get(key, force=force)
    if res is None:
        return None
    try:
        return model.model_validate_json(res)
    except ValidationError as e:
        log.error("failed to validate model", key=key, model=model.__name__, json=res, exc_info=e)
        return None


@REQUEST_DURATION.labels("ZADD").time()
async def unique_list_add(
    name: str,
    item: str,
    score: int = 0,
    ttl: timedelta = timedelta(0),
) -> bool:
    added: int = redis.zadd(name, {item: score})
    if ttl.total_seconds() > 0:
        log.debug("setting ttl for unique list", name=name, ttl=ttl)
        redis.expire(name, time=ttl)
    return bool(added)


@REQUEST_DURATION.labels("ZRANGE").time()
async def unique_list_get(name: str) -> list[str]:
    try:
        return [
            i.decode("utf-8")  # type: ignore
            for i in redis.zrevrange(  # type: ignore
                name=name,
                start=0,
                end=-1,
                withscores=False,
            )
        ]
    except Exception as e:
        log.error("failed to get unique list", name=name, exc_info=e)
        return []


async def set_model(key: str, model: BaseModel, ttl: timedelta) -> bool:
    return await set(key, model.model_dump_json(exclude_none=True), ttl=ttl)


@REQUEST_DURATION.labels("EXPIRE").time()
async def set_ttl(key: str, ttl: timedelta) -> bool:
    try:
        if redis.expire(key, time=ttl):
            return True
        return False
    except Exception as e:
        log.error("failed to set cache ttl", key=key, exc_info=e)
        return False


@REQUEST_DURATION.labels("PFCOUNT").time()
async def unique_count(key: str) -> int:
    try:
        return redis.pfcount(key)
    except Exception as e:
        log.error("failed to pfadd", key=key, exc_info=e)
        return False


@REQUEST_DURATION.labels("PFADD").time()
async def unique_add(key: str, value: str) -> bool:
    try:
        res = redis.pfadd(key, value)
        log.debug("redis command", command="PFADD", key=key, value=value, res=res)
        return bool(res)
    except Exception as e:
        log.error("failed to pfadd", key=key, exc_info=e)
        return False


@REQUEST_DURATION.labels("SET").time()
async def set(key: str, value: str, ttl: timedelta) -> bool:
    try:
        if redis.set(key, value, ex=int(ttl.total_seconds())):
            return True
        return False
    except Exception as e:
        log.error("failed to set cache", key=key, exc_info=e)
        return False


@REQUEST_DURATION.labels("GET").time()
async def get(key: str, force: bool = False) -> Optional[str]:
    try:
        if bypass := instrumentation.NO_CACHE.get(False):
            log.debug("cache bypassed", key=key, bypass=bypass)
            return None
        res: Optional[bytes] = redis.get(key)  # type: ignore
        if not res:
            log.debug("cache miss", key=key)
            return None
        log.debug("cache hit", key=key)
        return res.decode("utf-8")  # type: ignore
    except Exception as e:
        log.error("failed to get cache", key=key, exc_info=e)
        return None


if REDIS_URL:
    log.info("connected to redis", host=REDIS_URL)
    asyncio.create_task(ping())
else:
    log.info("running with local redis", storage=DB_PATH)
