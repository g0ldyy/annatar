import unittest

from pydantic import BaseModel

from annatar.human import find_episode


class SeasonEpisodeTest(BaseModel):
    file: str
    expected_result: int | None


class TestFindEpisode(unittest.TestCase):
    def test_matches_dot(self):
        result: int | None = find_episode("Foobar.S01.E01.mkv")
        self.assertEqual(result, 1)

    def test_matches_dash(self):
        result: int | None = find_episode("Foobar-S01-E02.mkv")
        self.assertEqual(result, 2)

    def test_matches_space(self):
        result: int | None = find_episode("Foobar S01 E03.mkv")
        self.assertEqual(result, 3)

    def test_matches_no_space(self):
        result: int | None = find_episode("FoobarS01E04.mkv")
        self.assertEqual(result, 4)

    def test_matches_no_leading_zero(self):
        result: int | None = find_episode("FoobarS1E5.mkv")
        self.assertEqual(result, 5)

    def test_matches_double_digit(self):
        result: int | None = find_episode("FoobarS01E10.mkv")
        self.assertEqual(result, 10)
