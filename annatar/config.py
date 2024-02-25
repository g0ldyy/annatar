import os
from base64 import b64decode

import structlog
from pydantic import BaseModel

log = structlog.get_logger()

APP_ID = os.getenv("APP_ID", "community.annatar.addon.stremio")
APP_NAME = os.getenv("APP_NAME", "Annatar")
ENV = os.getenv("ENV", "dev")
VERSION = os.getenv("BUILD_VERSION") or "0.0.1"


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
