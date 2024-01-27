from pydantic import BaseModel


class JackettResult(BaseModel):
    indexer: str
    title: str
    url: str
    externalUrl: str
    isFree: bool


async def search() -> list[JackettResult]:
    res = JackettResult(
        indexer="Test",
        title="Test",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        externalUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        isFree=True,
    )
    return [res]
