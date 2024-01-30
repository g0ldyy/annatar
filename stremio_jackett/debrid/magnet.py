import re


def get_info_hash(magnet_link: str) -> str | None:
    match = re.search("btih:([a-zA-Z0-9]+)", magnet_link)
    return match.group(1) if match else None
