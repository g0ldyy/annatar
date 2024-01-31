from typing import Optional

from pydantic import BaseModel


class DirectDL(BaseModel):
    path: str
    size: int
    link: str
    stream_link: str | None
    transcode_status: str


class DirectDLResponse(BaseModel):
    status: str
    content: Optional[list[DirectDL]] = None
