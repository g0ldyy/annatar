import unittest

from pydantic import BaseModel

from annatar.torrent import Torrent


class SearchQuery(BaseModel):
    name: str
    year: int = 0
    season: int = 0
    episode: int = 0


class TestScore(unittest.TestCase):
    def test_sorting_series_by_score_names(self):
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
            "Best Friends S01-E01 2160p",  # matches solely on quality
            "The Office S01-S10 1080p",  # matches on quality and series
            "The Office S5E10",  # matches on series and episode
            "Friends S01-S3",  # matches only name
            "Friends S3",  # matches only name
        ]

        results = sorted(
            torrents,
            key=lambda t: Torrent.parse_title(title=t).match_score(
                title=search_query.name,
                year=search_query.year,
                season=search_query.season,
                episode=search_query.episode,
            ),
            reverse=True,
        )

        self.assertEqual(results, torrents)

    def test_score_series(self):
        result = Torrent.parse_title(title="Friends S01-S10").score_series(season=5, episode=10)
        self.assertEqual(result, 3)

        result = Torrent.parse_title(title="Friends S04-E10").score_series(season=5, episode=10)
        self.assertEqual(result, -100)

        result = Torrent.parse_title(title="Friends S05").score_series(season=5, episode=10)
        self.assertEqual(result, 2)

        result = Torrent.parse_title(title="Friends S05-E10").score_series(season=5, episode=10)
        self.assertEqual(result, 1)
