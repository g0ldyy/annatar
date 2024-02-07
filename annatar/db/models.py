from typing import Optional

from pydantic import BaseModel


class Torrent(BaseModel):
    guid: str
    info_hash: str
    size: int
    title: str
    url: str
    seeders: int
    tracker: Optional[str] = ""

    @property
    def uuid(self) -> str:
        return f"torrent:{self.info_hash}"
