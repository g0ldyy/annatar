"""
This module is a wrapper around the redislite package to provide an async interface
to the redislite client. It is not a complete implementation of the redis client, but
it provides the most methods used in this project for interacting with a redis server.
As I use more methods, I will add them to this wrapper.
"""
import asyncio
from datetime import timedelta
from typing import Any, AsyncIterator

import redis
import redislite


class StrictRedis:
    def __init__(self, db_path: str | None = None):
        self.db = redislite.client.StrictRedis(db_path)

    async def ping(self):
        return self.db.ping()

    async def keys(self, pattern: str):
        return self.db.keys(pattern)

    async def zadd(
        self,
        name: str,
        mapping: dict,
        nx: bool = False,
        xx: bool = False,
        ch: bool = False,
        incr: bool = False,
        gt: bool = False,
        lt: bool = False,
    ):
        return self.db.zadd(name, mapping, nx, xx, ch, incr, gt, lt)

    async def zrevrangebyscore(
        self, name: str, max: float, min: float, start: int, num: int, withscores: bool = False
    ):
        return self.db.zrevrangebyscore(name, max, min, start, num, withscores)

    async def expire(self, key: str, time: timedelta | int):
        return self.db.expire(key, time)

    async def pfcount(self, key: str):
        return self.db.pfcount(key)

    async def pfadd(self, key: str, value: str):
        return self.db.pfadd(key, value)

    async def set(self, key: str, value: str, ex: timedelta | int | None = None, nx: bool = False):
        return self.db.set(key, value, ex=ex, nx=nx)

    async def hset(self, key: str, field: str, value: str):
        return self.db.hset(key, field, value)

    async def hmset(self, key: str, mapping: dict):
        return self.db.hmset(key, mapping)

    async def hget(self, key: str, field: str):
        return self.db.hget(key, field)

    async def hgetall(self, key: str):
        return self.db.hgetall(key)

    async def ttl(self, key: str):
        return self.db.ttl(key)

    async def get(self, key: str):
        return self.db.get(key)

    async def flushall(self):
        return self.db.flushall()

    async def publish(self, channel: str, message: str):
        return self.db.publish(channel, message)

    def pubsub(self):
        return PubSub(self.db.pubsub())


class PubSub:
    def __init__(self, base: redis.client.PubSub):
        self.pubsub = base

    async def subscribe(self, channel: str):
        return self.pubsub.subscribe(channel)

    async def listen(self) -> AsyncIterator[Any]:
        self.pubsub.listen()
        while True:
            message = self.pubsub.get_message(ignore_subscribe_messages=True, timeout=0.10)
            if message is None:
                await asyncio.sleep(1)
                continue
            yield message

    async def unsubscribe(self, channel: str):
        return self.pubsub.unsubscribe(channel)

    async def publish(self, channel: str, message: str):
        return self.publish(channel, message)

    async def get_message(self):
        return self.get_message()

    async def close(self):
        return self.close()
