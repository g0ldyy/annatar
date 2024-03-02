import unittest

from pydantic import BaseModel

from annatar.torrent import Torrent


class SearchQuery(BaseModel):
    name: str
    year: int = 0
    season: int = 0
    episode: int = 0


class TestNameMatches(unittest.TestCase):
    def test_name_matches_when_random_non_words_are_in_the_title(self):
        wanted = "Friends"
        title = "Friends? S01-S10 COMPLETE 4k"
        result = Torrent.parse_title(title=title).matches_name(title=wanted)
        self.assertTrue(result, f"{title} should match {wanted}")

    def test_name_does_not_match(self):
        wanted = "Just Friends"
        titles = [
            "Just Pals 2005 Comedy HD",
            "Jesting Friends 2005 720p BRRip",
            "Just Fr1ends Romantic 2005 DVDrip",
            "Gusted Friends 2005 1080p BluRay",
            "Just Friends of Friends 2005 WebDL 1080p",
            "Just Frenz 2005 Comedy HDRip",
            "Juxtoppo Friends 2005 4K UHD",
            "Just Buds 2005 Comedy 720p MKV",
            "Just Amigos 2005 FullHD 1080p",
            "Just Scarry Fiends 2005 Horror 720p",
        ]

        for i, title in enumerate(titles):
            result = Torrent.parse_title(title=title).matches_name(title=wanted)
            self.assertFalse(result, f"test({i}) {title} should not match {wanted}")

    def test_name_matches_typos(self):
        title = "Freinds S01-S10 COMPLETE 4k"
        result = Torrent.parse_title(title=title).matches_name(title="Friends")
        self.assertTrue(result)

    def test_name_matches_mixed_case_and_non_words_and_typos(self):
        title = "Fr!eNdS S01-S10 COMPLETE 4k"
        result = Torrent.parse_title(title=title).matches_name(title="Friends")
        self.assertTrue(result)


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
