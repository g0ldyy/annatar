from typing import Any

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore
from opentelemetry.instrumentation.requests import RequestsInstrumentor  # type: ignore

from stremio_jackett import jackett
from stremio_jackett.debrid.rd import get_movie_rd_links
from stremio_jackett.stremio import Stream, StreamResponse

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
    jacket_results = await jackett.search()
    get_movie_rd_links
    return StreamResponse(streams=[Stream()])

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
