from pydantic import BaseModel, Field


class Torrent(BaseModel):
    guid: str
    info_hash: str
    size: int
    title: str
    seeders: int
    tracker: str | None = None
    imdb: int | None = None
    match_score: int = Field(0, exclude=True)
