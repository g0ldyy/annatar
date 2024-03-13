from pydantic import BaseModel, Field


class CachedFile(BaseModel):
    name: str
    size: int


class CachedMagnet(BaseModel):
    name: str
    info_hash: str = Field(..., alias="hashString")
    files: list[CachedFile] = Field(..., alias="files", default_factory=list)


class CachedResponse(BaseModel):
    success: bool
    value: dict[str, CachedMagnet]


class TorrentFile(BaseModel):
    id: str
    name: str
    download_url: str = Field(..., alias="downloadUrl")
    size: int
    download_percent: int = Field(..., alias="downloadPercent")


class TorrentInfo(BaseModel):
    id: str
    name: str
    hash_string: str = Field(..., alias="hashString")
    upload_ratio: float = Field(..., alias="uploadRatio")
    server_id: str = Field(..., alias="serverId")
    wait: bool
    peers_connected: int = Field(..., alias="peersConnected")
    status: int
    total_size: int = Field(..., alias="totalSize")
    files: list[TorrentFile]
