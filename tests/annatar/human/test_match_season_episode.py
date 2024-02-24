import pytest
from pydantic import BaseModel

from annatar.human import match_season_episode


class SeasonEpisodeTest(BaseModel):
    season: int
    episode: int
    file: str
    expected_result: bool


# Define your test data as a dictionary
test_data: dict[str, SeasonEpisodeTest] = {
    "matchs_season_only": SeasonEpisodeTest(
        season=1,
        episode=2,
        file="The.Mandalorian.S01E01.1080p",
        expected_result=False,
    ),
    "matches_episode_only": SeasonEpisodeTest(
        season=2,
        episode=2,
        file="The.Mandalorian.S01E02.1080p",
        expected_result=False,
    ),
    "matches_none": SeasonEpisodeTest(
        season=2,
        episode=2,
        file="The.Mandalorian.S01E01.1080p",
        expected_result=False,
    ),
    "matches_both": SeasonEpisodeTest(
        season=1,
        episode=1,
        file="The.Mandalorian.S01.E01.1080p",
        expected_result=True,
    ),
    "matches_both_without_leading_zero": SeasonEpisodeTest(
        season=9,
        episode=9,
        file="The.Mandalorian.S9.E9.1080p",
        expected_result=True,
    ),
    "matches_both_with_no_space_between": SeasonEpisodeTest(
        season=9,
        episode=9,
        file="The.Mandalorian.S9E9.1080p",
        expected_result=True,
    ),
}


@pytest.mark.parametrize("name, t", test_data.items())
def test_function(name: str, t: SeasonEpisodeTest):
    result: bool = match_season_episode(season_episode=[t.season, t.episode], file=t.file)
    assert result == t.expected_result
