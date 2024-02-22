from pydantic import BaseModel


class Stream(BaseModel):
    name: str = "Annatar"
    title: str
    url: str


class StreamResponse(BaseModel):
    streams: list[Stream]
    error: str | None = None
