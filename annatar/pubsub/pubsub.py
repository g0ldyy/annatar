from enum import Enum
from typing import AsyncGenerator, Type, TypeVar

import structlog
from prometheus_client import Counter
from pydantic import BaseModel

from annatar import instrumentation
from annatar.database.db import redis

log = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

REDIS_MESSAGES_CONSUMED = Counter(
    name="redis_pubsub_messages_consumed",
    documentation="Total messages consumed on redis",
    labelnames=["topic"],
    registry=instrumentation.registry(),
)

REDIS_MESSAGES_PUBLISHED = Counter(
    name="redis_pubsub_messages_published",
    documentation="Total messages published on redis",
    labelnames=["topic"],
    registry=instrumentation.registry(),
)


class Topic(str, Enum):
    TorrentSearchResult = "events:v1:torrent:search_result"
    TorrentAdded = "events:v1:torrent:added"


async def lock(key: str, timeout: int = 10) -> bool:
    return bool(await redis.set(key, "locked", nx=True, ex=timeout))


async def publish(topic: Topic, msg: str) -> int:
    REDIS_MESSAGES_PUBLISHED.labels(topic).inc()
    return await redis.publish(topic, msg)


async def consume_topic(topic: Topic, model: Type[T]) -> AsyncGenerator[T, None]:
    """
    Consume a topic indefinitely. If timeout is set then consumption will end
    if nothing has been received for the duration of the timeout.
    """
    log.info("begin consuming topic", topic=topic)
    pubsub = redis.pubsub()
    await pubsub.subscribe(topic)
    async for message in pubsub.listen():
        if message is None:
            continue
        if message.get("type", "") != "message":
            continue
        data = message.get("data", {})
        try:
            yield model.model_validate_json(data)
            REDIS_MESSAGES_CONSUMED.labels(topic).inc()
        except Exception as e:
            log.error(
                "failed to deserialize message from queue",
                topic=topic,
                model=model,
                object=data,
                exc_info=e,
            )
    log.info("closing subscription to topic", topic=topic)
    pubsub.close()
