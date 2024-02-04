import pytest
from pydantic import BaseModel

from annatar.human import score_name


class PriorityTest(BaseModel):
    query: str
    year: int
    filename: str
    expected_score: int


# Define your test data as a dictionary
test_data: dict[str, PriorityTest] = {
    "no_match": PriorityTest(
        query="Jumanji",
        year=1995,
        filename="no match whatsoever",
        expected_score=0,
    ),
    "year_only": PriorityTest(
        query="Jumanji",
        year=1995,
        filename="Another movie in 1995.avi",
        expected_score=20,
    ),
    "quality_only": PriorityTest(
        query="Jumanji",
        year=1995,
        filename="Another movie in 1985 1080p.avi",
        expected_score=5,
    ),
    "name_only_match": PriorityTest(
        query="Jumanji",
        year=1995,
        filename="Jumanji.s01.e02.mkv",
        expected_score=100,
    ),
    "name_2160p": PriorityTest(
        query="Jumanji",
        year=1995,
        filename="Jumanji.2160p.mkv",
        expected_score=110,
    ),
    "name_4k": PriorityTest(
        query="Jumanji",
        year=1995,
        filename="Jumanji.4k.mkv",
        expected_score=110,
    ),
    "name_1080p": PriorityTest(
        query="Jumanji",
        year=1995,
        filename="Jumanji.1080p.mkv",
        expected_score=105,
    ),
    "name_year": PriorityTest(
        query="Jumanji",
        year=1995,
        filename="Jumanji.1995.mkv",
        expected_score=120,
    ),
    "name_year_2160p": PriorityTest(
        query="Jumanji",
        year=1995,
        filename="Jumanji.2160p.1995.mkv",
        expected_score=130,
    ),
    "name_year_1080p": PriorityTest(
        query="Jumanji",
        year=1995,
        filename="Jumanji.1080p.1995.mkv",
        expected_score=125,
    ),
}


@pytest.mark.parametrize("name, t", test_data.items())
def test_function(name: str, t: PriorityTest):
    result: int = score_name(t.query, t.year, t.filename)
    assert result == t.expected_score
