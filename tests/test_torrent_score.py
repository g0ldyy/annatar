import json

from pydantic import BaseModel

from annatar.torrent import Torrent


class SearchQuery(BaseModel):
    name: str
    year: int = 0
    season: int = 0
    episode: int = 0


def test_sorting_series_by_score_names():
    search_query = SearchQuery(name="Friends", year=1994, season=5, episode=10)

    torrents = [
        "Friends S01-S10 COMPLETE 4k",
        "Friends S01-S10 COMPLETE 1080p",
        "Friends S01-S10 1080p",
        "Friends S01-S10 COMPLETE",
        "Friends Season 1-10 COMPLETE",
        "Friends S05 COMPLETE 2160p",
        "Friends S5",
        "Friends S05E10 1080p",
        "Friends S01-S3",  # matches only name
        "Friends S3",  # matches only name
        "Best Friends S01-S10 2160p",  # matches solely on quality
        "The Office S01-S10 1080p",  # matches on quality and series
        "The Office S5E10",  # matches on series and episode
    ]

    results = sorted(
        torrents,
        key=lambda t: Torrent.parse_title(title=t).score_with(
            title=search_query.name,
            year=search_query.year,
            season=search_query.season,
            episode=search_query.episode,
        ),
        reverse=True,
    )

    assert results == torrents


def test_score_series():
    result = Torrent.parse_title(title="Friends S01-S10").score_series(season=5, episode=10)
    assert result == 3
    result = Torrent.parse_title(title="Friends S04-E10").score_series(season=5, episode=10)
    assert result == -10
    result = Torrent.parse_title(title="Friends S05").score_series(season=5, episode=10)
    assert result == 2
    result = Torrent.parse_title(title="Friends S05-E10").score_series(season=5, episode=10)
    assert result == 1
