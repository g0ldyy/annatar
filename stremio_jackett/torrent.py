from pydantic import BaseModel


class Torrent(BaseModel):
    guid: str
    info_hash: str
    size: int
    title: str
    url: str
    seeders: int
