import os
from base64 import b64decode
from datetime import datetime

import structlog
from pydantic import BaseModel

log = structlog.get_logger()
DEFAULT_INDEXERS = "yts,eztv,kickasstorrents-ws,thepiratebay,therarbg,torrentgalaxy,bitsearch,limetorrents,badasstorrents"


APP_ID = os.getenv("APP_ID", "community.annatar.addon.stremio")
APP_NAME = os.getenv("APP_NAME", "Annatar")
BUILD_VERSION: str = os.getenv("BUILD_VERSION", "UNKNOWN")
ENV = os.getenv("ENV", "dev")
HOST: str = os.getenv("LISTEN_HOST", "0.0.0.0")
JACKETT_INDEXERS_LIST = (os.getenv("JACKETT_INDEXERS") or DEFAULT_INDEXERS).split(",")
PORT: int = int(os.getenv("LISTEN_PORT", "8000"))
PROM_DIR = os.getenv(
    "PROMETHEUS_MULTIPROC_DIR", f"/tmp/annatar.metrics-{datetime.now().timestamp()}"
)
VERSION = os.getenv("BUILD_VERSION") or "0.0.1"
TORRENT_TITLE_MATCH_THRESHOLD = float(os.getenv("TORRENT_TITLE_MATCH_THRESHOLD") or 0.85)


class UserConfig(BaseModel):
    debrid_service: str
    debrid_api_key: str
    indexers: list[str]
    resolutions: list[str] = ["4K", "QHD", "1080p", "720p", "480p"]
    max_results: int = 5

    @staticmethod
    def defaults() -> "UserConfig":
        return UserConfig(
            debrid_service="",
            debrid_api_key="",
            max_results=5,
            indexers=[],
        )


def parse_config(b64config: str) -> UserConfig:
    if not b64config:
        return UserConfig.defaults()
    try:
        return UserConfig.model_validate_json(b64decode(b64config))
    except Exception as e:
        log.error("Unrecognized config parsing error", exc_info=e)
        return UserConfig.defaults()
