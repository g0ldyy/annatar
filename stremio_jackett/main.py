import json
from typing import Any, Optional

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore
from opentelemetry.instrumentation.requests import RequestsInstrumentor  # type: ignore

from stremio_jackett import jackett
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


@app.get("/stream/{type:str}/{id:str}")
async def search(
    type: str,
    id: str,
    streamService: str,
    jackettUrl: str,
    jackettApiKey: str,
    debridApiKey: str,
    maxResults: int = 5,
) -> StreamResponse:
    media_id = id.replace(".json", "").split(":")
    season = int(media_id[0]) if len(media_id) > 0 else None
    episode = int(media_id[1]) if len(media_id) > 1 else None
    if season:
        print(f"Searching for {type} {media_id}")
    else:
        print(f"Searching for {type} Season:{season} Episode:{episode}")

    media_info = await get_media_info(id=media_id[0], type=type)
    print(f"Found Media Info: {json.dumps(media_info)}")

    jackett_results: list[JackettResult] = await jackett.search(
        debrid_api_key=debridApiKey,
        jackett_url=jackettUrl,
        jackett_api_key=jackettApiKey,
        service=streamService,
        max_results=maxResults,
        search_query=jackett.SearchQuery(
            name=media_info.name,
            type=type,
            season=season,
            episode=episode,
        ),
    )

    torrent_links: list[str] = [l.url for l in jackett_results]
    rd_links: dict[str, Optional[rd.UnrestrictedLink]] = await rd.get_movie_rd_links(
        torrent_links=torrent_links, debrid_token=debridApiKey, season_episode=id
    )
    streams: list[Stream] = [
        Stream(
            title=media_info.name,
            url=link.download,
        )
        for link in rd_links
    ]
    return StreamResponse(streams=streams)

    # return {
    #     "streams": [
    #         {
    #             "title": "Test",
    #             "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    #             "externalUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    #             "isFree": True,
    #         }
    #     ]
    # }


# routes.get("/:params/stream/:type/:id", async (req, res) => {
# 	try {
# 		const paramsJson = JSON.parse(atob(req.params.params));
# 		const type = req.params.type;
# 		const id = req.params.id.replace(".json", "").split(":");
# 		const service = paramsJson.streamService;
# 		const jackettUrl = paramsJson.jackettUrl;
# 		const jackettApi = paramsJson.jackettApiKey;
# 		const debridApi = paramsJson.debridApiKey;
# 		const maxResults = clamp(1, paramsJson.maxResults || 5, 15);

# 		const mediaName = await getName(id[0], type);
# 		if (type === "movie") {
# 			console.log(`Movie request. ID: ${id[0]} Name: ${mediaName}`);
# 			const torrentInfo = await fetchResults(debridApi, jackettUrl, jackettApi, service, maxResults, {
# 				name: mediaName,
# 				type: type,
# 			});
# 			respond(res, { streams: torrentInfo });
# 		}
# 		if (type === "series") {
# 			console.log(
# 				`Series request. ID: ${id[0]} Name: "${mediaName}" Season: ${getNum(id[1])} Episode: ${getNum(
# 					id[2],
# 				)}`,
# 			);
# 			const torrentInfo = await fetchResults(debridApi, jackettUrl, jackettApi, service, maxResults, {
# 				name: mediaName,
# 				type: type,
# 				season: getNum(id[1]),
# 				episode: getNum(id[2]),
# 			});
# 			respond(res, { streams: torrentInfo });
# 		}
# 	} catch (e) {
# 		console.log(e);
# 		respond(res, noResults);
# 	}
# });


if __name__ == "__main__":
    FastAPIInstrumentor.instrument_app(app)
    RequestsInstrumentor().instrument()
    app.run()
