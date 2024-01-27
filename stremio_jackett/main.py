import json
from typing import Any, Optional

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore
from opentelemetry.instrumentation.requests import RequestsInstrumentor  # type: ignore

from stremio_jackett import human, jackett
from stremio_jackett.debrid import rd
from stremio_jackett.jackett import JackettResult
from stremio_jackett.stremio import Stream, StreamResponse, get_media_info

app = FastAPI()


@app.get("/manifest.json")
async def get_manifest() -> dict[str, Any]:
    return {
        "id": "community.blockloop.jackettpy",
        "icon": "https://i.imgur.com/wEYQYN8.png",
        "version": "0.1.0",
        "catalogs": [],
        "resources": ["stream"],
        "types": ["movie", "series"],
        "name": "JackettPy",
        "description": "Stremio Jackett Addon",
        "behaviorHints": {
            "configurable": "true",
        },
    }


@app.get("/stream/{type:str}/{id:str}.json")
async def search(
    type: str,
    id: str,
    streamService: str,
    jackettUrl: str,
    jackettApiKey: str,
    debridApiKey: str,
    maxResults: int = 5,
) -> StreamResponse:
    title_id = id.split(":")[0]
    print(f"Searching for {type} {id}")

    media_info = await get_media_info(id=title_id, type=type)
    print(f"Found Media Info: {media_info.model_dump_json()}")

    q = jackett.SearchQuery(
        name=media_info.name,
        type=type,
    )

    if type == "series":
        q.season = int(id.split(":")[1])
        q.episode = int(id.split(":")[2])

    jackett_results: list[JackettResult] = await jackett.search(
        debrid_api_key=debridApiKey,
        jackett_url=jackettUrl,
        jackett_api_key=jackettApiKey,
        service=streamService,
        max_results=maxResults,
        search_query=q,
    )

    torrent_links: list[str] = [l.url for l in jackett_results]
    rd_links: dict[str, Optional[rd.UnrestrictedLink]] = await rd.get_movie_rd_links(
        torrent_links=torrent_links, debrid_token=debridApiKey, season_episode=id
    )
    streams: list[Stream] = [
        Stream(
            title=media_info.name,
            url=link.download,
            name=f"{link.filename}\n{human.bytes(float(link.filesize))}",
        )
        for _, link in rd_links.items()
        if link
    ]
    return StreamResponse(streams=streams)


if __name__ == "__main__":
    FastAPIInstrumentor.instrument_app(app)  # type: ignore
    RequestsInstrumentor().instrument()  # type: ignore

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)  # type: ignore
