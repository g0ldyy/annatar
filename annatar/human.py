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
            return f"{num:3.2f} {unit}B"
        num /= 1024.0
    return f"{num:.2f} GB"


def match_season(season: int, file: str) -> bool:
    return bool(re.search(rf"\bS{season:02}\D", file, re.IGNORECASE)) or bool(
        re.search(rf"\bS{season}\D", file, re.IGNORECASE)
    )


def is_video(file: str, size: int) -> bool:
    if size < 100000000:  # 100MB
        return False
    return file.split(".")[-1] in VIDEO_EXTENSIONS


def match_episode(episode: int, file: str) -> bool:
    return find_episode(file) == episode


def find_episode(file: str) -> int | None:
    match = re.search(r"[^A-Z]E(\d\d?)\b", file, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def match_season_episode(season: int, episode: int, file: str) -> bool:
    matches_season = match_season(season, file)
    matches_episode = match_episode(episode, file)

    log.debug(
        "pattern match result",
        matches_season=matches_season,
        matches_episode=matches_episode,
        file=file,
    )
    return matches_season and matches_episode


def rank_quality(name: str) -> int:
    """
    Sort items by quality
    """
    for index, quality in enumerate(reversed(PRIORITY_WORDS)):
        if re.search(quality, name, re.IGNORECASE):
            return index * 5
    return 0


def arrange_into_rows(strings: list[str], rows: int) -> str:
    split_index = (len(strings) + 1) // rows
    first_row = strings[:split_index]
    second_row = strings[split_index:]
    return "\n".join([" ".join(first_row), " ".join(second_row)])
