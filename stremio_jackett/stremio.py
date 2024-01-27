from pydantic import BaseModel


class Stream(BaseModel):
    name: str = "Jackett Debrid"
    title: str
    url: str


class StreamResponse(BaseModel):
    streams: list[Stream]
