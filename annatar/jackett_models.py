from typing import List, Optional

from pydantic import BaseModel


class ListIndexersResponse(BaseModel):
    pass


class Category(BaseModel):
    name: str
    id: int

    @staticmethod
    def find_by_name(name: str) -> Optional["Category"]:
        if name == "movie":
            return MOVIES
        if name == "series":
            return SERIES
        return None


MOVIES = Category(name="movie", id=2000)
SERIES = Category(name="series", id=5000)


class SearchQuery(BaseModel):
    name: str
    type: str
    year: int
    imdb_id: str
    season: Optional[int] = None
    episode: Optional[int] = None


class SearchResult(BaseModel):
    Tracker: Optional[str] = None
    TrackerId: Optional[str] = None
    Title: str
    Guid: str
    Link: Optional[str] = ""
    Category: List[int] = []
    Size: int = 0
    TVDBId: Optional[str] = None
    Imdb: int | None = 0
    TMDb: Optional[str] = None
    TraktId: Optional[str] = None
    Languages: List[str] = []
    Subs: List[str] = []
    Year: Optional[int] = None
    Seeders: int = 0
    InfoHash: Optional[str] = None
    MagnetUri: Optional[str] = None


class SearchResults(BaseModel):
    Results: list[SearchResult] = []
