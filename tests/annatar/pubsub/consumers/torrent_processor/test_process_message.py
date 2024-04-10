import unittest
from hashlib import sha1
from random import randint
from unittest import mock
from uuid import uuid4

import structlog
from aioresponses import aioresponses
from redislite.client import StrictRedis

from annatar import magnet
from annatar.database import db, odm
from annatar.pubsub.consumers.torrent_processor import (
    process_message,
    resolve_magnet_link,
)
from annatar.pubsub.events import TorrentSearchCriteria, TorrentSearchResult
from annatar.torrent import Category, TorrentMeta

log = structlog.get_logger(__name__)


def new_info_hash(s: str) -> str:
    return sha1(s.encode()).hexdigest().upper()


def mock_imdb() -> str:
    return f"tt{randint(1000000, 9999999)}"


def mock_search_result(title: str) -> TorrentSearchResult:
    meta: TorrentMeta = TorrentMeta.parse_title(title)
    imdb: str = mock_imdb()
    season: int = meta.season[0] if meta.season else 0
    return TorrentSearchResult(
        info_hash=new_info_hash(title),
        title=title,
        guid=uuid4().hex,
        imdb=imdb,
        year=meta.year[0] if meta.year else 0,
        category=[5000],
        indexer="mock",
        search_criteria=TorrentSearchCriteria(
            query=meta.title,
            imdb=imdb,
            year=meta.year[0] if meta.year else 0,
            category=Category.Movie if not season else Category.Series,
        ),
    )


class map_matched_result(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        db.redis = StrictRedis()
        self.assertTrue(db.redis.ping())

    async def asyncTearDown(self):
        db.redis.flushall()

    @mock.patch("annatar.torrent.TorrentMeta.match_score")
    async def test_does_not_allow_low_meta_scores(self, mock_match_score):
        title = "The Lord of the Rings The Return of the King 2003 1080p X265"
        search_result = mock_search_result(title)

        mock_match_score.return_value = 0
        await process_message(search_result)
        mock_match_score.assert_called_once()
        torrents = await odm.list_torrents(imdb=search_result.imdb)
        self.assertNotIn(search_result.info_hash, torrents)

    async def test_does_not_allow_mismatched_imdb(self):
        title = "The Lord of the Rings The Return of the King TS 2003 1080p X265"
        search_result = mock_search_result(title)
        search_result.search_criteria.imdb = mock_imdb()

        await process_message(search_result)
        torrents = await odm.list_torrents(imdb=search_result.imdb)
        self.assertNotIn(search_result.info_hash, torrents)


class ProcessMessage(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        db.redis = StrictRedis()
        self.assertTrue(db.redis.ping())

    async def asyncTearDown(self):
        db.redis.flushall()

    async def test_does_not_store_low_scores(self):
        title = "The Lord of the Rings The Return of the King 2003 1080p X265"
        search_result = mock_search_result(title)
        search_result.search_criteria.imdb = mock_imdb()

        await process_message(search_result)
        torrents = await odm.list_torrents(imdb=search_result.imdb)
        self.assertNotIn(search_result.info_hash, torrents)

    async def test_stores_movies(self):
        title = "The Lord of the Rings The Return of the King 2003 1080p X265"
        search_result = mock_search_result(title)

        await process_message(search_result)
        torrents = await odm.list_torrents(imdb=search_result.imdb)
        self.assertIn(search_result.info_hash, torrents)

    async def test_stores_whole_season(self):
        title = "Fargo S01 2020 1080p HULU WEB-DL DDP5 1 H 264"
        search_result = mock_search_result(title)

        await process_message(search_result)
        torrents = await odm.list_torrents(imdb=search_result.imdb, season=1, episode=0)
        self.assertIn(search_result.info_hash, torrents)

    async def test_stores_whole_series(self):
        title = "Fargo S01-S05 2020 1080p HULU WEB-DL DDP5 1 H 264"
        search_result = mock_search_result(title)

        await process_message(search_result)
        for season in range(1, 6):
            torrents = await odm.list_torrents(imdb=search_result.imdb, season=season, episode=0)
            self.assertIn(search_result.info_hash, torrents, f"season {season}")

    async def test_stores_all_episodes(self):
        title = "Fargo S01 E01-E05 2020 1080p HULU WEB-DL DDP5 1 H 264"
        search_result = mock_search_result(title)

        await process_message(search_result)
        for episode in range(1, 6):
            torrents = await odm.list_torrents(
                imdb=search_result.imdb,
                season=1,
                episode=episode,
            )
            self.assertIn(search_result.info_hash, torrents, f"episode {episode}")

    async def test_sets_title(self):
        title = "Fargo S01E01 2020 1080p HULU WEB-DL DDP5 1 H 264"
        search_result = mock_search_result(title)

        await process_message(search_result)

        dbtitle = await odm.get_torrent_title(search_result.info_hash)
        self.assertEqual(dbtitle, title)

    @mock.patch("annatar.pubsub.consumers.torrent_processor.resolve_magnet_link")
    async def test_resolves_magnet_links(self, mock_resolve_magnet_link: mock.MagicMock):
        title = "The Hobbit The Battle of the Five Armies 2014 1080p X265"
        search_result = mock_search_result(title)
        info_hash = search_result.info_hash
        search_result.info_hash = ""
        search_result.magnet_link = "http://example.tld"

        mock_resolve_magnet_link.return_value = info_hash
        await process_message(search_result)

        torrents = await odm.list_torrents(imdb=search_result.imdb)
        self.assertIn(info_hash, torrents)


class ResolveMagnetLink(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        db.redis = StrictRedis()
        self.assertTrue(db.redis.ping())

    async def asyncTearDown(self):
        db.redis.flushall()

    async def test_resolves_magnet_links(self):
        guid = uuid4().hex
        link = "https://example.tld"
        info_hash = new_info_hash(guid)
        magnet_link = magnet.make_magnet_link(info_hash)

        with aioresponses() as mock_http:
            mock_http.get(
                link,
                status=302,
                headers={"location": magnet_link},
            )
            result = await resolve_magnet_link(guid, link)

        self.assertEqual(result, info_hash)

    async def test_returns_existing_magnet_link(self):
        guid = uuid4().hex
        info_hash = new_info_hash(guid)
        magnet_link = magnet.make_magnet_link(info_hash)

        with aioresponses() as mock_http:
            result = await resolve_magnet_link(guid, magnet_link)
            mock_http.assert_not_called()
            self.assertEqual(result, info_hash)
