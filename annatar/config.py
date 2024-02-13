from base64 import b64decode

import structlog
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

log = structlog.get_logger()

APP_ID = "community.annatar.addon"


class UserConfig(BaseModel):
    debrid_service: str
    debrid_api_key: str
    indexers: list[str]
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
    try:
        return UserConfig.model_validate_json(b64decode(b64config))
    except ValidationError as e:
        log.warning("error decoding config", error=e, errro_type=type(e).__name__)
        raise RequestValidationError(
            errors=e.errors(include_url=False, include_input=False),
        )
    except Exception as e:
        log.error("Unrecognized error", error=e)
        raise HTTPException(status_code=500, detail="Internal server error")
