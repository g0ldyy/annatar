import pytest
from pydantic import BaseModel

from annatar.human import find_episode


class SeasonEpisodeTest(BaseModel):
    file: str
    expected_result: int | None


# Define your test data as a dictionary
test_data: dict[str, SeasonEpisodeTest] = {
    "matches_dot": SeasonEpisodeTest(
        file="Foobar.S01.E01.mkv",
        expected_result=1,
    ),
    "matches_dash": SeasonEpisodeTest(
        file="Foobar-S01-E02.mkv",
        expected_result=2,
    ),
    "matches_space": SeasonEpisodeTest(
        file="Foobar S01 E03.mkv",
        expected_result=3,
    ),
    "matches_no_space": SeasonEpisodeTest(
        file="FoobarS01E04.mkv",
        expected_result=4,
    ),
    "matches_no_leading_zero": SeasonEpisodeTest(
        file="FoobarS1E5.mkv",
        expected_result=5,
    ),
    "matches_double_digit": SeasonEpisodeTest(
        file="FoobarS01E10.mkv",
        expected_result=10,
    ),
}


@pytest.mark.parametrize("name, t", test_data.items())
def test_function(name: str, t: SeasonEpisodeTest):
    result: int | None = find_episode(t.file)
    assert result == t.expected_result
