from typing import Optional

from pydantic import BaseModel


class Torrent(BaseModel):
    guid: str
    info_hash: str
    size: int
    title: str
    url: str
    seeders: int
    tracker: Optional[str] = None
    imdb: Optional[int] = None
