import structlog
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)


class CacheResponse(BaseModel):
    cached_items: list[str] = Field(..., alias="cachedItems", default_factory=list)


class AddMagnetResponse(BaseModel):
    request_id: str = Field(..., alias="requestId")
    file_name: str = Field(..., alias="fileName")
    site: str = ""
    status: str
    original_link: str = Field(..., alias="originalLink")
    url: str


class TorrentInfo(BaseModel):
    status: str
    amount: int
    request_id: str = Field(..., alias="requestId")
    file_name: str = Field(..., alias="fileName")
    file_size: int = Field(..., alias="fileSize")
    server: str
    is_directory: bool = Field(..., alias="isDirectory")


class CloudStatusResponse(BaseModel):
    requests: list[TorrentInfo]


class CloudHistoryItem(BaseModel):
    request_id: str = Field(..., alias="requestId")
    file_name: str = Field(..., alias="fileName")
    site: str
    status: str
    original_link: str = Field(..., alias="originalLink")
    is_directory: bool = Field(..., alias="isDirectory")
    created_on: str = Field(..., alias="createdOn")
    server: str


class CachedFileInfo(BaseModel):
    name: str
    size: int
    link: str
