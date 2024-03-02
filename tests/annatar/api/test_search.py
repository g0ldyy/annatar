from unittest import TestCase
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from annatar.main import app

pytestmark = pytest.mark.integration


@pytest.mark.integration
class TestAPISearch(TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("annatar.database.odm")
    def test_name_exists(self, mock_odm):
        imdb = "tt0111161"
        mock_odm.list_torrents.return_value = ["ABCDEFG"]
        response = self.client.get(f"/search/imdb/movie/{imdb}")
        self.assertEqual(200, response.status_code)
        self.assertIn("name", response.json())
