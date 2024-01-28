from typing import Optional

import aiohttp
from pydantic import BaseModel


class Stream(BaseModel):
    name: str = "Jackett Debrid"
    title: str
    url: str


class StreamResponse(BaseModel):
    streams: list[Stream]
    error: str | None = None


# export async function getName(id, type) {
# 	if (typeof id !== "string") {
# 		return id;
# 	}

# 	const res = await fetch(`https://v3-cinemeta.strem.io/meta/${type}/${id}.json`);
# 	const name = (await res.json()).meta.name;

# 	return name;
# }


class MediaInfo(BaseModel):
    id: str
    type: str
    name: str

    genres: Optional[list[str]] = None
    director: Optional[list[str]] = None
    cast: Optional[list[str]] = None
    poster: Optional[str] = None
    posterShape: Optional[str] = None
    background: Optional[str] = None
    logo: Optional[str] = None
    description: Optional[str] = None
    # A.k.a. year, e.g. "2000" for movies and "2000-2014" or "2000-" for TV shows
    releaseInfo: Optional[str] = None
    imdbRating: Optional[str] = None
    # ISO 8601, e.g. "2010-12-06T05:00:00.000Z"
    released: Optional[str] = None
    runtime: Optional[str] = None
    language: Optional[str] = None
    country: Optional[str] = None
    awards: Optional[str] = None
    website: Optional[str] = None


async def get_media_info(id: str, type: str) -> MediaInfo | None:
    async with aiohttp.ClientSession() as session:
        api_url = f"https://v3-cinemeta.strem.io/meta/{type}/{id}.json"
        async with session.get(api_url) as response:
            if response.status not in range(200, 300):
                print(f"Error getting media info: {response.status}")
                return None
            response_json = await response.json()
            meta = response_json["meta"]
            media_info = MediaInfo(**meta)
            return media_info


# type Meta struct {
# 	ID   string `json:"id"`
# 	Type string `json:"type"`
# 	Name string `json:"name"`

# 	// Optional
# 	Genres      []string `json:"genres,omitempty"`
# 	Director    []string `json:"director,omitempty"`
# 	Cast        []string `json:"cast,omitempty"`
# 	Poster      string   `json:"poster,omitempty"`
# 	PosterShape string   `json:"posterShape,omitempty"`
# 	Background  string   `json:"background,omitempty"`
# 	Logo        string   `json:"logo,omitempty"`
# 	Description string   `json:"description,omitempty"`
# 	ReleaseInfo string   `json:"releaseInfo,omitempty"` // A.k.a. *year*. E.g. "2000" for movies and "2000-2014" or "2000-" for TV shows
# 	IMDbRating  string   `json:"imdbRating,omitempty"`
# 	Released    string   `json:"released,omitempty"` // ISO 8601, e.g. "2010-12-06T05:00:00.000Z"
# 	Runtime     string   `json:"runtime,omitempty"`
# 	Language    string   `json:"language,omitempty"`
# 	Country     string   `json:"country,omitempty"`
# 	Awards      string   `json:"awards,omitempty"`
# 	Website     string   `json:"website,omitempty"`
# }
