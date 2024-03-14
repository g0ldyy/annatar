import asyncio
from abc import ABC, abstractmethod
from typing import Type, TypeVar

import structlog
from pydantic import BaseModel

from annatar.pubsub import pubsub
from annatar.pubsub.events import Topic

log = structlog.get_logger(__name__)

TBaseModel = TypeVar("TBaseModel", bound=BaseModel)


class BaseConsumer(ABC):
    num_workers: int
    queue: asyncio.Queue
    topic: Topic

    def __init__(
        self, topic: Topic, num_workers: int, model: Type[TBaseModel], max_queue_depth: int = 0
    ):
        self.topic = topic
        self.num_workers = num_workers
        self.queue = asyncio.Queue[model](maxsize=max_queue_depth)
        self.model = model

    async def run(self):
        while True:
            workers: list[asyncio.Task] = []
            try:
                workers = [
                    asyncio.create_task(self.process_queue(), name=f"{self.__class__.__name__}_{i}")
                    for i in range(self.num_workers)
                ] + [
                    asyncio.create_task(
                        pubsub.consume_topic(
                            topic=self.topic,
                            model=self.model,
                            queue=self.queue,
                            consumer=self.__class__.__name__,
                        )
                    )
                ]

                await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)

                log.error("torrent processor worker exited unexpectedly")
            except asyncio.exceptions.CancelledError:
                break
            except Exception as err:
                log.error("torrent processor error", exc_info=err)
                await asyncio.sleep(5)
            finally:
                for w in workers:
                    if not w.done():
                        w.cancel()

    async def process_queue(self):
        while True:
            result = await self.queue.get()
            if not result:
                continue
            try:
                await self.receive_message(result)
            except asyncio.exceptions.CancelledError:
                break
            except Exception as err:
                log.error("torrent processor error", exc_info=err)
                await asyncio.sleep(5)
            finally:
                if result:
                    self.queue.task_done()

    @abstractmethod
    async def receive_message(self, result: Type[TBaseModel]):
        ...
