from annatar.human import score_name
from annatar.jackett_models import SearchQuery


def test_sorting_series_by_score_names():
    search_query = SearchQuery(
        name="Friends",
        year=1994,
        type="series",
        season="5",
        episode="10",
    )

    torrents = [
        "Friends S01-S10 COMPLETE 4k",
        "Friends S01-S10 COMPLETE 1080p",
        "Friends S01-S10 1080p",
        "Friends S05 COMPLETE 2160p",
        "Friends S01-S10 COMPLETE",
        "Friends S5",
        "Friends S05E10 1080p",
        "Friends S3",
        "Friends S01-S3",
        "Best Friends S01-S10 2160p",
        "The Office S01-S10 1080p",
        "The Office S5E10",
    ]

    results = sorted(
        torrents,
        key=lambda t: score_name(search_query, t),
        reverse=True,
    )

    assert results == torrents


def test_sorting_movies_by_score_names():
    search_query = SearchQuery(
        name="Pirates of the Caribbean: Dead Man's Chest",
        year=2006,
        type="movie",
    )

    torrents = [
        "Pirates of the Caribbean Dead Man's Chest (2006) (2160p DSNP WEBRip x265 HEVC 10bit EAC3",
        "Pirates of the Caribbean Dead Man's Chest (2006) 2160p BRRip 5.1 10Bit x265 -YTS",
        "Pirates of the Caribbean: Dead Man's Chest 2006 2160p bluray YTS",
        "Pirates of the Caribbean Dead Man s Chest 2006 1080p H264 DolbyD 5 1 nickarad",
        "Pirates of the Caribbean Dead Man s Chest 2006 1080p BrRip x264 YIFY",
        "Pirates of the Caribbean: Dead Man's Chest (2006) 1080p BrRip x2",
        "Pirates of the Caribbean Dead Man s Chest 2006 1080p 10bit Bluray x265 HEVC Org NF DDP",
        "Pirates of the Caribbean Dead Man's Chest (2006) 720p BRRip x264 -YTS",
        "Pirates of the Caribbean: Dead Man's Chest (2006) 720p BrRip x26...",
        "Pirates of the Caribbean: Dead Man's Chest (2032) 4K BrRip x26...",
        "Piratess eat dead things in 4K 2006",
    ]

    results = sorted(
        torrents,
        key=lambda t: score_name(search_query, t),
        reverse=True,
    )

    assert results == torrents
