import re

import structlog

from annatar.jackett_models import SearchQuery

log = structlog.get_logger(__name__)

PRIORITY_WORDS: list[str] = [r"\b(4K|2160p)\b", r"\b1080p\b", r"\b720p\b"]
QUALITIES: dict[str, str] = {
    "4K": r"\b(4K|2160p)\b",
    "1080p": r"\b1080p\b",
    "720p": r"\b720p\b",
    "480p": r"\b480p\b",
}
VIDEO_EXTENSIONS = [
    "3g2",
    "3gp",
    "avi",
    "flv",
    "m2ts",
    "m4v",
    "mk3d",
    "mkv",
    "mov",
    "mp2",
    "mp4",
    "mpe",
    "mpeg",
    "mpg",
    "mpv",
    "ogm",
    "ts",
    "webm",
    "wmv",
]


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


def match_season(season: int, file: str) -> bool:
    return bool(re.search(rf"\bS{season:02}\D", file, re.IGNORECASE)) or bool(
        re.search(rf"\bS{season}\D", file, re.IGNORECASE)
    )


def is_video(file: str) -> bool:
    return file.split(".")[-1] in VIDEO_EXTENSIONS


def match_episode(episode: int, file: str) -> bool:
    return find_episode(file) == episode


def find_episode(file: str) -> int | None:
    match = re.search(rf"[^A-Z]E(\d\d?)\b", file, re.IGNORECASE)
    if match:
        return int(match.group(1))


def match_season_episode(season_episode: list[int], file: str) -> bool:
    matches_season = match_season(season_episode[0], file)
    matches_episode = match_episode(season_episode[1], file)

    log.debug(
        "pattern match result",
        matches_season=matches_season,
        matches_episode=matches_episode,
        file=file,
    )
    return matches_season and matches_episode


def get_season_range(name: str) -> list[int]:
    match = re.search(rf"\bS(\d+)[-\s]S?(\d+)\b", name, re.IGNORECASE)
    if match:
        begin = int(match.group(1))
        # python range ends are non-inclusive so +1
        end = 1 + int(match.group(2))
        if begin == end:
            return [begin]
        return list(range(begin, end))
    elif match := re.search(rf"\bS(\d+)\b", name, re.IGNORECASE):
        return [int(match.group(1))]
    return []


def has_season(name: str, season: str) -> bool:
    season_range = get_season_range(name)
    if season_range and int(season) in season_range:
        return True
    return False


def get_episode(name: str) -> int | None:
    match = re.search(rf"\bE(\d\d?)\b", name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def has_episode(name: str, episode: str) -> bool:
    return int(episode) == get_episode(name)


def score_by_quality(name: str) -> int:
    """
    Sort items by quality
    """
    for index, quality in enumerate(reversed(PRIORITY_WORDS)):
        if re.search(quality, name, re.IGNORECASE):
            return index * 5
    return 0


def score_name(query: SearchQuery, name: str) -> int:
    """
    Sort items by quality and how well they match the query pattern
    """

    score: int = 0
    name_pattern: str = re.sub(r"\W+", r"\\W+", query.name)
    if re.search(name_pattern, name, re.IGNORECASE):
        # name match is highest priority
        if re.search(rf"^{name_pattern}\W", name, re.IGNORECASE):
            # name match at the beginning of the string is the best
            score += 1000
        else:
            # name match anywhere in the string is still good but produces
            # false positives for series with common names like Friends
            score += 200
    else:
        # If the name doesn't match then gtfo
        return -1000

    if re.search(rf"\W{query.year}\W", name):
        # year match is a good indicator and sometimes helps filter out
        # rebooted series with the same name
        score += 500
    if query.season and query.episode:
        # this is a series so we have to match on season and episode
        seasons = get_season_range(name)
        if len(seasons) > 1 and int(query.season) in seasons:
            # this is likely a complete series so it should be highest priority
            score += 200
        elif has_season(name, query.season):
            # This torrent contains this season either as a range or a single season
            score += 50
            if episode := get_episode(name):
                if episode == int(query.episode):
                    # matches the episode
                    score += 100
                else:
                    # wrong episode
                    score -= 1000
        else:
            # This torrent does not contain this season
            score -= 70
    # finally we check the stream quality
    for index, quality in enumerate(reversed(PRIORITY_WORDS)):
        if re.search(quality, name, re.IGNORECASE):
            score += index * 100
            break
    log.debug(
        "torrent score set",
        search_query=query,
        name_pattern=name_pattern,
        score=score,
    )
    return score
