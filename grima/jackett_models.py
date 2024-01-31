from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class SearchQuery(BaseModel):
    name: str
    type: str
    year: Optional[str] = None
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
