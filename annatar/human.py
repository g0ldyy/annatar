import re

import structlog

log = structlog.get_logger(__name__)

PRIORITY_WORDS: list[str] = [r"\b(4K|2160p)\b", r"\b1080p\b", r"\b720p\b"]
QUALITIES: dict[str, str] = {
    "4K": r"\b(4K|2160p)\b",
    "1080p": r"\b1080p\b",
    "720p": r"\b720p\b",
    "480p": r"\b480p\b",
}


def grep_quality(s: str) -> str:
    """
    Get the quality of the file
    """
    for name, quality in QUALITIES.items():
        if re.search(quality, s, re.IGNORECASE):
            return name
    return ""


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
    s = season_episode[0]
    e = season_episode[1]
    matches_season: bool = bool(re.search(rf"\bS{s:02}\D", file, re.IGNORECASE)) or bool(
        re.search(rf"\bS{s}\D", file, re.IGNORECASE)
    )

    matches_episode: bool = bool(re.search(rf"E{e:02}\b", file, re.IGNORECASE)) or bool(
        re.search(rf"E{e}\b", file, re.IGNORECASE)
    )
    log.debug(
        "pattern match result",
        matches_season=matches_season,
        matches_episode=matches_episode,
        file=file,
    )
    return matches_season and matches_episode


# sort items by quality
def score_name(query: str, year: int, name: str) -> int:
    """
    Sort items by quality and how well they match the query pattern
    :param query: original search quality
    :param name: result name
    """

    score: int = 0
    name_pattern: str = re.sub(r"\W+", r"\\W+", query)
    if re.search(name_pattern, name, re.IGNORECASE):
        score += 100
    if re.search(rf"\W{year}\W", name):
        score += 20
    for index, quality in enumerate(reversed(PRIORITY_WORDS)):
        if re.search(quality, name, re.IGNORECASE):
            score += index * 5
            break
    log.debug(
        "torrent score set",
        search_query=query,
        name_pattern=name_pattern,
        score=score,
    )
    return score
