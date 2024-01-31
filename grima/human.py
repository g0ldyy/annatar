import re

import structlog

log = structlog.get_logger(__name__)


def bytes(num: float) -> str:
    """
    Get human readable bytes string for bytes
    Example: (1024*5) -> 5K | (1024*1024*5) -> 5M | (1024*1024*1024*5) -> 5G
    """
    for unit in ("", "K", "M"):
        if abs(num) < 1024.0:
            return f"{num:3.2f}{unit}B"
        num /= 1024.0
    return f"{num:.2f}GB"


def pretty_season_episode(season_episode: list[int]) -> str:
    return f"""S{"E".join([str(x) for x in season_episode])}"""


def match_season_episode(season_episode: list[int], file: str) -> bool:
    pattern = r"S0?{s}\s?E0?{e}".format(
        s=season_episode[0],
        e=season_episode[1],
    )

    result = bool(re.search(pattern, file, re.IGNORECASE))
    log.debug("pattern match result", pattern=pattern, file=file, result=result)
    return result
