import asyncio
import json
import os
from datetime import datetime, timedelta
from sqlite3 import Row
from typing import Optional, Type, TypeVar

import aiosqlite
import structlog
from pydantic import BaseModel

from annatar.logging import timestamped

log = structlog.get_logger(__name__)

DB_PATH: str = os.path.abspath(os.getenv("DB_PATH", "annatar.db"))
CONNECTION_STRING: str = f"{DB_PATH}"

T = TypeVar("T", bound=BaseModel)


async def initial_seed():
    async with aiosqlite.connect(CONNECTION_STRING) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS kvs (
                key TEXT PRIMARY KEY
                ,value TEXT REQUIRED
                ,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ,expires TIMESTAMP REQUIRED
            );
            """
        )
        await db.commit()


@timestamped(["key"])
async def get_str(key: str) -> Optional[str]:
    async with aiosqlite.connect(CONNECTION_STRING) as db:
        cursor: aiosqlite.Cursor = await db.execute(
            """
            SELECT value FROM kvs
            WHERE key = ?
            AND expires > datetime('now')
            LIMIT 1
            """,
            (key,),
        )
        await db.commit()
        row: Optional[Row] = await cursor.fetchone()
        if row:
            log.info("cache hit", key=key)
            return row[0]
        log.info("cache miss", key=key)
        return None


async def get_list(key: str, model: Type[T]) -> list[T]:
    row: Optional[str] = await get_str(key)
    if row:
        return [model.model_validate_json(x) for x in json.loads(row)]
    return []


async def get(key: str, model: Type[T]) -> Optional[T]:
    row: Optional[str] = await get_str(key)
    if row:
        return model.model_validate_json(row)
    return None


@timestamped(["key"])
async def put(key: str, value: BaseModel, ttl: timedelta = timedelta(days=1)) -> bool:
    async with aiosqlite.connect(CONNECTION_STRING) as db:
        await db.execute(
            """
            INSERT INTO kvs (key, value, expires)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value, expires = EXCLUDED.expires;
            """,
            (key, value.model_dump_json(), datetime.now() + ttl),
        )
        await db.commit()
    return True


async def delete(key: str) -> bool:
    async with aiosqlite.connect(CONNECTION_STRING) as db:
        await db.execute("DELETE FROM kvs WHERE key = ?", (key,))
    return True


async def init() -> asyncio.Task[None]:
    log.info("initializing the database", conn=CONNECTION_STRING)
    await initial_seed()

    async def cleanup_expired(interval_seconds: int):
        try:
            while True:
                async with aiosqlite.connect(CONNECTION_STRING) as db:
                    await db.execute("DELETE FROM kvs WHERE expired < datetime('now')")
                    await db.commit()
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            log.info("shutting down the database cleanup task")

    return asyncio.create_task(cleanup_expired(60))
