from pydantic import BaseModel, Field


class Stream(BaseModel):
    name: str = "Annatar"
    title: str
    url: str


class StreamResponse(BaseModel):
    streams: list[Stream]
    cached: bool = Field(default=False, exclude=True)
    error: str | None = None
