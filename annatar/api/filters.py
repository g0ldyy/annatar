import re
from typing import Callable

from pydantic import BaseModel, Field

from annatar.torrent import TorrentMeta


class Filter(BaseModel):
    id: str
    name: str
    apply: Callable[[TorrentMeta], bool] = Field(..., exclude=True)
    category: str

    def __str__(self) -> str:
        return self.name


ALL = (
    [
        # Resolutions
        Filter(
            id="4k",
            name="4K (2160p)",
            apply=lambda meta: "4K" in meta.resolution,
            category="Resolution",
        ),
        Filter(
            id="qhd",
            name="QHD (1440p)",
            apply=lambda meta: "1440p" in meta.resolution,
            category="Resolution",
        ),
        Filter(
            id="1080p",
            name="1080p",
            apply=lambda meta: "1080p" in meta.resolution,
            category="Resolution",
        ),
        Filter(
            id="720p",
            name="720p",
            apply=lambda meta: "720p" in meta.resolution,
            category="Resolution",
        ),
        Filter(
            id="480p",
            name="480p",
            apply=lambda meta: "480p" in meta.resolution,
            category="Resolution",
        ),
        Filter(
            id="unknown_resolution",
            name="Unknown Resolution",
            apply=lambda meta: meta.resolution == [],
            category="Resolution",
        ),
        # Video Quality
        Filter(
            id="yts",
            name="YTS",
            apply=lambda meta: bool(re.search(r"(YTS|YIFY)", meta.raw_title, re.IGNORECASE)),
            category="Video Quality",
        ),
        Filter(
            id="remux",
            name="REMUX",
            apply=lambda meta: meta.remux,
            category="Video Quality",
        ),
        Filter(
            id="hdr",
            name="HDR",
            apply=lambda meta: meta.hdr,
            category="Video Quality",
        ),
        Filter(
            id="x265",
            name="H.265 (HEVC)",
            apply=lambda meta: "H.265" in meta.codec,
            category="Video Quality",
        ),
        Filter(
            id="x264",
            name="H.264 (AVC)",
            apply=lambda meta: "H.264" in meta.codec,
            category="Video Quality",
        ),
        Filter(
            id="ten_bit",
            name="10bit",
            apply=lambda meta: [10] == meta.bitDepth,
            category="Video Quality",
        ),
    ]
    + [
        # Languages
        # Filter(
        #     id=lang,
        #     name=lang,
        #     category="Language",
        #     apply=lambda meta: lang in [lang.lower() for lang in meta.language],
        # )
        # for lang in [
        #     "English",
        #     "French",
        #     "German",
        #     "Italian",
        #     "Japanese",
        #     "Korean",
        #     "Mandarin",
        #     "Russian",
        #     "Spanish",
        #     "Hindi",
        # ]
    ]
)


def by_id(id: str) -> Filter:
    return next(filter(lambda f: f.id == id, ALL))


def by_category(category: str) -> list[Filter]:
    return list(filter(lambda f: f.category == category, ALL))
