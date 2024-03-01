import unittest

from pydantic import BaseModel

from annatar.human import match_season_episode


class SeasonEpisodeTest(BaseModel):
    season: int
    episode: int
    file: str
    expected_result: bool


class TestMatchSeasonEpisode(unittest.TestCase):
    def test_matches_season_only(self):
        result: bool = match_season_episode(
            season=1, episode=2, file="The.Mandalorian.S01E01.1080p"
        )
        self.assertFalse(result)

    def test_matches_episode_only(self):
        result: bool = match_season_episode(
            season=2, episode=2, file="The.Mandalorian.S01E02.1080p"
        )
        self.assertFalse(result)

    def test_matches_none(self):
        result: bool = match_season_episode(
            season=2, episode=2, file="The.Mandalorian.S01E01.1080p"
        )
        self.assertFalse(result)

    def test_matches_both(self):
        result: bool = match_season_episode(
            season=1, episode=1, file="The.Mandalorian.S01.E01.1080p"
        )
        self.assertTrue(result)

    def test_matches_both_without_leading_zero(self):
        result: bool = match_season_episode(season=9, episode=9, file="The.Mandalorian.S9.E9.1080p")
        self.assertTrue(result)

    def test_matches_both_with_no_space_between(self):
        result: bool = match_season_episode(season=9, episode=9, file="The.Mandalorian.S9E9.1080p")
        self.assertTrue(result)
