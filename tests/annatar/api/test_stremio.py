from unittest import TestCase

import pytest
from fastapi.testclient import TestClient

from annatar.main import app

pytestmark = pytest.mark.integration


@pytest.mark.integration
class TestManifest(TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_name_exists(self):
        response = self.client.get("/manifest.json")
        self.assertEqual(200, response.status_code)
        self.assertIn("name", response.json())
