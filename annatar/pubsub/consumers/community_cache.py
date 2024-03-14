import asyncio

import structlog
from pydantic import BaseModel

from annatar.pubsub import events

log = structlog.get_logger(__name__)


class CommunityCacheProcessor(BaseModel):
    async def run(self, num_workers: int) -> None:
        while True:
            log.info("start consuming", num_workers=num_workers)
            tasks: list[asyncio.Task] = []
            try:
                queue = asyncio.Queue[events.SearchRequest]()
                tasks = [asyncio.create_task(process_queue(queue)) for i in range(num_workers)] + [
                    asyncio.create_task(
                        events.SearchRequest.listen(queue, "community-cache-processor")
                    )
                ]
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            except asyncio.CancelledError:
                log.info("cancelled")
                break
            except Exception as e:
                log.error("exited unexpectedly", exc_info=e)
                continue
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()


async def process_queue(queue: asyncio.Queue[events.SearchRequest]) -> None:
    while True:
        search_request = await queue.get()
        # Process request
        queue.task_done()
