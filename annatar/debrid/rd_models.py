import asyncio
from os import getenv
from typing import Optional

import aiohttp
from pydantic import BaseModel

from annatar.torrent import Torrent


class InstantFile(BaseModel):
    id: int
    filename: str
    filesize: int


class StreamableFile(BaseModel):
    id: int
    link: str
    size: int


class TorrentFile(BaseModel):
    id: int
    path: str
    bytes: int = 0
    selected: int = 0


class TorrentInfo(BaseModel):
    id: str
    filename: str
    original_filename: str
    hash: str
    bytes: int
    original_bytes: int
    host: str
    split: int
    progress: int
    status: str
    added: str
    files: list[TorrentFile]
    links: list[str]
    ended: Optional[str] = None
    speed: Optional[int] = None
    seeders: Optional[int] = None


class UnrestrictedLink(BaseModel):
    id: str
    torrent: Torrent
    filename: str
    mimeType: str  # Mime Type of the file, guessed by the file extension
    filesize: int  # Filesize in bytes, 0 if unknown
    link: str  # Original link
    host: str  # Host main domain
    chunks: int  # Max Chunks allowed
    crc: int  # Disable / enable CRC check
    download: str  # Generated link
    streamable: int  # Is the file streamable on website
