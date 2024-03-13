import re


def parse_magnet_link(uri: str) -> str:
    match = re.search("btih:([a-zA-Z0-9]+)", uri)
    if match:
        return match.group(1).upper()
    raise ValueError(f"Invalid magnet link: {uri}")


def make_magnet_link(info_hash: str) -> str:
    return f"magnet:?xt=urn:btih:{info_hash}"
