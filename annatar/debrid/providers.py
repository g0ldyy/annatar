from typing import Optional

from annatar.debrid.debrid_service import DebridService
from annatar.debrid.premiumize_provider import PremiumizeProvider
from annatar.debrid.real_debrid_provider import RealDebridProvider

_providers: list[DebridService] = [
    RealDebridProvider(api_key=""),
    PremiumizeProvider(api_key=""),
]


def register_provider(prov: "DebridService"):
    _providers.append(prov)


def list_providers() -> list[dict[str, str]]:
    return [{"id": p.id(), "name": p.name()} for p in _providers]


def get_provider(provider_name: str, api_key: str) -> Optional[DebridService]:
    for p in _providers:
        if p.id() == provider_name:
            return p.__class__(api_key)
    return None
