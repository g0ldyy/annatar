from typing import Optional

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
    added: str
    bytes: int
    filename: str
    hash: str
    host: str
    id: str
    links: list[str]
    progress: float
    split: int
    status: str

    ended: Optional[str] = None
    files: Optional[list[TorrentFile]] = None
    original_bytes: Optional[int] = None
    original_filename: Optional[str] = None
    seeders: Optional[int] = None
    speed: Optional[int] = None


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
