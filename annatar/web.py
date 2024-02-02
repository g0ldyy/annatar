from pydantic import BaseModel, Field

from annatar.jackett_models import Indexer


class FormConfig(BaseModel):
    available_indexers: list[Indexer] = Field(..., alias="availableIndexers")
    available_debrid_providers: list[dict[str, str]] = Field(..., alias="availableDebridProviders")
