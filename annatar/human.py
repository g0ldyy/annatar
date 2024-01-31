import re

import structlog
from structlog.contextvars import bound_contextvars

log = structlog.get_logger(__name__)

PRIORITY_WORDS: list[str] = [r"\b(4K|2160p)\b", r"\b1080p\b", r"\b720p\b"]


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


# sort items by quality
def sort_priority(query: str, name: str) -> int:
    """
    Sort items by quality and how well they match the query pattern
    :param query: original search quality
    :param name: result name
    """

    name_pattern: str = re.sub(r"\W+", r"\\W+", query)
    with bound_contextvars(
        search_query=query,
        name_pattern=name_pattern,
    ):
        log.debug("set torrent priority")

        priority: int = 50
        reason: str = "no priority matches"
        for index, quality in enumerate(PRIORITY_WORDS):
            if re.search(quality, name, re.IGNORECASE):
                if re.search(name_pattern, name, re.IGNORECASE):
                    priority = index
                    reason = f"matched {quality} and name"
                else:
                    priority = index + 10
                    reason = f"matched {quality}, mismatch name"
        log.debug("torrent priority set", priority=priority, reason=reason)
        return priority
