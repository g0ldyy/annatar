from pydantic import BaseModel


class JackettResult(BaseModel):
    indexer: str
    title: str
    url: str
    externalUrl: str
    isFree: bool


class SearchQuery(BaseModel):
    name: str
    type: str
    season: int | None = None
    episode: int | None = None


# debridApi, jackettUrl, jackettApi, service, maxResults
async def search(
    debrid_api_key: str,
    jackett_url: str,
    jackett_api_key: str,
    service: str,
    search_query: SearchQuery,
    max_results: int,
) -> list[JackettResult]:
    res = JackettResult(
        indexer="Test",
        title="Test",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        externalUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        isFree=True,
    )
    return [res]
