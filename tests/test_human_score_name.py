import pytest
from pydantic import BaseModel

from annatar.human import score_name
from annatar.jackett_models import SearchQuery


class PriorityTest(BaseModel):
    query: SearchQuery
    filename: str
    expected_score: int


test_movie_data: dict[str, PriorityTest] = {
    "no_match": PriorityTest(
        query=SearchQuery(name="Jumanji", year=1995, type="movie"),
        filename="no match whatsoever",
        expected_score=0,
    ),
    "year_only": PriorityTest(
        query=SearchQuery(name="Jumanji", year=1995, type="movie"),
        filename="Another movie in 1995.avi",
        expected_score=20,
    ),
    "quality_only": PriorityTest(
        query=SearchQuery(name="Jumanji", year=1995, type="movie"),
        filename="Another movie in 1985 1080p.avi",
        expected_score=5,
    ),
    "name_only_match": PriorityTest(
        query=SearchQuery(name="Jumanji", year=1995, type="movie"),
        filename="Jumanji.s01.e02.mkv",
        expected_score=100,
    ),
    "name_2160p": PriorityTest(
        query=SearchQuery(name="Jumanji", year=1995, type="movie"),
        filename="Jumanji.2160p.mkv",
        expected_score=110,
    ),
    "name_4k": PriorityTest(
        query=SearchQuery(name="Jumanji", year=1995, type="movie"),
        filename="Jumanji.4k.mkv",
        expected_score=110,
    ),
    "name_1080p": PriorityTest(
        query=SearchQuery(name="Jumanji", year=1995, type="movie"),
        filename="Jumanji.1080p.mkv",
        expected_score=105,
    ),
    "name_year": PriorityTest(
        query=SearchQuery(name="Jumanji", year=1995, type="movie"),
        filename="Jumanji.1995.mkv",
        expected_score=120,
    ),
    "name_year_2160p": PriorityTest(
        query=SearchQuery(name="Jumanji", year=1995, type="movie"),
        filename="Jumanji.2160p.1995.mkv",
        expected_score=130,
    ),
    "name_year_1080p": PriorityTest(
        query=SearchQuery(name="Jumanji", year=1995, type="movie"),
        filename="Jumanji.1080p.1995.mkv",
        expected_score=125,
    ),
}


@pytest.mark.parametrize("name, t", test_movie_data.items())
def test_movies(name: str, t: PriorityTest):
    result: int = score_name(t.query, t.filename)
    assert result == t.expected_score


test_series_data: dict[str, PriorityTest] = {
    "no_match": PriorityTest(
        query=SearchQuery(
            name="The X-Files",
            year=1993,
            type="series",
            season="2",
            episode="5",
        ),
        filename="no match whatsoever",
        expected_score=-70,
    ),
    "match name and season": PriorityTest(
        query=SearchQuery(
            name="The X-Files",
            year=1993,
            type="series",
            season="2",
            episode="5",
        ),
        filename="The X-Files.s02.e05.mkv",
        expected_score=170,
    ),
    "match name, year, season": PriorityTest(
        query=SearchQuery(
            name="The X-Files",
            year=1993,
            type="series",
            season="2",
            episode="5",
        ),
        filename="The X-Files.s02.e05.1993.mkv",
        expected_score=190,
    ),
    "complete series with dash": PriorityTest(
        query=SearchQuery(
            name="The X-Files",
            year=1993,
            type="series",
            season="2",
            episode="5",
        ),
        filename="The X-Files S01-S10 COMPLETE SEASON",
        expected_score=200,
    ),
    "complete series space": PriorityTest(
        query=SearchQuery(
            name="The X-Files",
            year=1993,
            type="series",
            season="2",
            episode="5",
        ),
        filename="The X-Files S01 S10 COMPLETE SEASON",
        expected_score=200,
    ),
    "season range inclusive": PriorityTest(
        query=SearchQuery(
            name="The X-Files",
            year=1993,
            type="series",
            season="2",
            episode="5",
        ),
        filename="The X-Files S01 S02 COMPLETE SEASON",
        expected_score=200,
    ),
    "season range non-inclusive": PriorityTest(
        query=SearchQuery(
            name="The X-Files",
            year=1993,
            type="series",
            season="4",
            episode="5",
        ),
        filename="The X-Files S01 S02 COMPLETE SEASON",
        expected_score=30,
    ),
    "single season": PriorityTest(
        query=SearchQuery(
            name="The X-Files",
            year=1993,
            type="series",
            season="2",
            episode="5",
        ),
        filename="The X-Files S02",
        expected_score=150,
    ),
}


@pytest.mark.parametrize("name, t", test_series_data.items())
def test_function(name: str, t: PriorityTest):
    result: int = score_name(t.query, t.filename)
    assert result == t.expected_score
