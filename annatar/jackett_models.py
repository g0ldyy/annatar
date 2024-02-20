from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from annatar.torrent import Torrent


class ScoredTorrent(BaseModel):
    torrent: Torrent
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
    supports_imdb: bool

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
    Indexer(
        name="YTS",
        id="yts",
        categories=[MOVIES],
        supports_imdb=True,
    ),
    Indexer(
        name="EZTV",
        id="eztv",
        categories=[SERIES],
        supports_imdb=True,
    ),
    Indexer(
        name="Kickass Torrents",
        id="kickasstorrents-ws",
        categories=[MOVIES, SERIES],
        supports_imdb=False,
    ),
    Indexer(
        name="The Pirate Bay",
        id="thepiratebay",
        categories=[MOVIES, SERIES],
        supports_imdb=True,
    ),
    Indexer(
        name="RARBG",
        id="therarbg",
        categories=[MOVIES, SERIES],
        supports_imdb=False,
    ),
    Indexer(
        name="Torrent Galaxy",
        id="torrentgalaxy",
        categories=[MOVIES, SERIES],
        supports_imdb=True,
    ),
    Indexer(
        name="LimeTorrents",
        id="limetorrents",
        categories=[MOVIES, SERIES],
        supports_imdb=False,
    ),
    Indexer(
        name="Badass Torrents",
        id="badasstorrents",
        categories=[MOVIES, SERIES],
        supports_imdb=False,
    ),
    Indexer(
        name="BitSearch",
        id="bitsearch",
        categories=[MOVIES, SERIES],
        supports_imdb=False,
    ),
]


class SearchQuery(BaseModel):
    name: str
    type: str
    year: int
    imdb_id: str
    season: Optional[str] = None
    episode: Optional[str] = None


class SearchResult(BaseModel):
    FirstSeen: Optional[datetime] = None
    Tracker: Optional[str] = None
    TrackerId: Optional[str] = None
    TrackerType: Optional[str] = None
    CategoryDesc: Optional[str] = None
    BlackholeLink: Optional[str] = None
    Title: str
    Guid: str
    Link: Optional[str] = ""
    Details: Optional[str] = None
    PublishDate: Optional[datetime] = None
    Category: List[int] = []
    Size: int = 0
    Grabs: Optional[int] = None
    Description: Optional[str] = None
    RageID: Optional[str] = None
    TVDBId: Optional[str] = None
    Imdb: int | None = 0
    TMDb: Optional[str] = None
    TVMazeId: Optional[str] = None
    TraktId: Optional[str] = None
    DoubanId: Optional[str] = None
    Genres: List[str] = []
    Languages: List[str] = []
    Subs: List[str] = []
    Year: Optional[int] = None
    Author: Optional[str] = None
    BookTitle: Optional[str] = None
    Publisher: Optional[str] = None
    Artist: Optional[str] = None
    Album: Optional[str] = None
    Label: Optional[str] = None
    Track: Optional[str] = None
    Seeders: int = 0
    Peers: Optional[int] = None
    Poster: Optional[str] = None
    InfoHash: Optional[str] = None
    MagnetUri: Optional[str] = None
    MinimumRatio: Optional[float] = None
    MinimumSeedTime: Optional[str] = None
    DownloadVolumeFactor: Optional[float] = None
    UploadVolumeFactor: Optional[float] = None
    Gain: Optional[float] = None


class SearchResults(BaseModel):
    Results: list[SearchResult] = []
