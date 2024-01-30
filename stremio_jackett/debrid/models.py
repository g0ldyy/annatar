from pydantic import BaseModel


class StreamLink(BaseModel):
    size: int
    name: str
    url: str
