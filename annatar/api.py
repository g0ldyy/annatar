import re
from typing import Optional

import structlog

from annatar import human, jackett
from annatar.debrid.models import StreamLink
from annatar.debrid.providers import DebridService
from annatar.jackett_models import Indexer, SearchQuery
from annatar.logging import timestamped
from annatar.meta.cinemeta import MediaInfo, get_media_info
from annatar.stremio import Stream, StreamResponse
from annatar.torrent import Torrent

log = structlog.get_logger(__name__)


@timestamped(["max_results", "jackett_url", "debrid", "imdb_id", "season_episode"])
async def search(
    type: str,
    max_results: int,
    jackett_url: str,
    jackett_api_key: str,
    debrid: DebridService,
    imdb_id: str,
    season_episode: list[int] = [],
    indexers: list[str] = [],
) -> StreamResponse:
    media_info: Optional[MediaInfo] = await get_media_info(id=imdb_id, type=type)
    if not media_info:
        log.error("error getting media info", type=type, id=imdb_id)
        return StreamResponse(streams=[], error="Error getting media info")
    log.info("found media info", type=type, id=id, media_info=media_info.model_dump())

    q = SearchQuery(
        name=media_info.name,
        type=type,
        year=int(re.split(r"\D", (media_info.releaseInfo or ""))[0]),
    )

    if type == "series" and len(season_episode) == 2:
        q.season = str(season_episode[0])
        q.episode = str(season_episode[1])

    torrents: list[Torrent] = await jackett.search_indexers(
        max_results=max(10, max_results),
        jackett_url=jackett_url,
        jackett_api_key=jackett_api_key,
        search_query=q,
        imdb=int(imdb_id.replace("tt", "")),
        timeout=60,
        indexers=[Indexer.find_by_id(i) for i in indexers],
    )

    links: list[StreamLink] = await debrid.get_stream_links(
        torrents=torrents,
        season_episode=season_episode,
        max_results=max_results,
    )

    sorted_links: list[StreamLink] = list(
        reversed(
            sorted(
                links,
                key=lambda x: human.score_name(q.name, q.year, x.name),
            )
        )
    )

    streams: list[Stream] = [
        Stream(
            title="\n".join(
                [
                    link.name,
                    f"💾{human.bytes(float(link.size))}",
                ]
            ),
            url=link.url,
            name=f"[{debrid.short_name()}+] {human.grep_quality(link.name)}",
        )
        for link in sorted_links
    ]
    return StreamResponse(streams=streams)
