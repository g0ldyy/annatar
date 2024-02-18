from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ScoredTorrent(BaseModel):
    info_hash: str
    score: int = 0


class Torrents(BaseModel):
    items: list[str]


class ListIndexersResponse(BaseModel):
    pass


class Category(BaseModel):
    name: str
    id: int

    @staticmethod
    def find_by_name(name: str) -> Optional["Category"]:
        if name == "movie":
            return MOVIES
        elif name == "series":
            return SERIES
        return None


MOVIES = Category(name="movie", id=2000)
SERIES = Category(name="series", id=5000)


class Indexer(BaseModel):
    id: str
    name: str
    categories: list[Category]

    def supports(self, category: str) -> bool:
        for cat in self.categories:
            if cat.name == category:
                return True
        return False

    @staticmethod
    def find_by_name(name: str) -> Optional["Indexer"]:
        for indexer in ALL_INDEXERS:
            if indexer.name == name:
                return indexer
        return None

    @staticmethod
    def find_by_id(id: str) -> Optional["Indexer"]:
        for indexer in ALL_INDEXERS:
            if indexer.id == id:
                return indexer
        return None

    @staticmethod
    def all() -> List["Indexer"]:
        return ALL_INDEXERS


# TODO: need to gather these from jackett on startup or take this as an env var
# and then verify on startup. Jackett will accept incorrect values though and
# just return no results
ALL_INDEXERS: list[Indexer] = [
    Indexer(name="YTS", id="yts", categories=[MOVIES]),
    Indexer(name="EZTV", id="eztv", categories=[SERIES]),
    Indexer(name="Kickass Torrents", id="kickasstorrents-ws", categories=[MOVIES, SERIES]),
    Indexer(name="The Pirate Bay", id="thepiratebay", categories=[MOVIES, SERIES]),
    Indexer(name="RARBG", id="therarbg", categories=[MOVIES, SERIES]),
    Indexer(name="Torrent Galaxy", id="torrentgalaxy", categories=[MOVIES, SERIES]),
]


class SearchQuery(BaseModel):
    name: str
    type: str
    year: int
    season: Optional[str] = None
    episode: Optional[str] = None


class SearchResult(BaseModel):
    FirstSeen: Optional[datetime]
    Tracker: Optional[str]
    TrackerId: Optional[str]
    TrackerType: Optional[str]
    CategoryDesc: Optional[str]
    BlackholeLink: Optional[str]
    Title: str
    Guid: str
    Link: Optional[str] = ""
    Details: Optional[str]
    PublishDate: Optional[datetime]
    Category: List[int]
    Size: int = 0
    Grabs: Optional[int]
    Description: Optional[str]
    RageID: Optional[str]
    TVDBId: Optional[str]
    Imdb: Optional[int]
    TMDb: Optional[str]
    TVMazeId: Optional[str]
    TraktId: Optional[str]
    DoubanId: Optional[str]
    Genres: List[str]
    Languages: List[str]
    Subs: List[str]
    Year: Optional[int]
    Author: Optional[str]
    BookTitle: Optional[str]
    Publisher: Optional[str]
    Artist: Optional[str]
    Album: Optional[str]
    Label: Optional[str]
    Track: Optional[str]
    Seeders: int = 0
    Peers: Optional[int]
    Poster: Optional[str]
    InfoHash: Optional[str]
    MagnetUri: Optional[str]
    MinimumRatio: Optional[float]
    MinimumSeedTime: Optional[str]
    DownloadVolumeFactor: Optional[float]
    UploadVolumeFactor: Optional[float]
    Gain: Optional[float]


class SearchResults(BaseModel):
    Results: list[SearchResult]
