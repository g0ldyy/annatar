import asyncio
from uuid import uuid4

from redislite.client import StrictRedis


class AsyncLockManager:
    def __init__(self, redis: StrictRedis, lock_key: str, delay: float = 0.05):
        self.redis = redis
        self.lock_key = lock_key
        self.lock_value = uuid4().hex
        self.delay = delay

    async def __aenter__(self):
        while True:
            acquired = self.redis.set(self.lock_key, self.lock_value, nx=True, ex=10)
            if acquired:
                return self
            await asyncio.sleep(self.delay)

    async def __aexit__(self, exc_type, exc, tb):
        if self.redis.get(self.lock_key) == self.lock_value:
            self.redis.delete(self.lock_key)
