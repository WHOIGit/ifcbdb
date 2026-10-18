from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from ninja.testing import TestClient

from api.api import api
from dashboard.models import Bin, Dataset

VALID_KEY = "test-key"


@override_settings(API_KEY=VALID_KEY)
class MostRecentBinTests(TestCase):
    "GET /api/most_recent_bin"

    def setUp(self):
        self.client = TestClient(api)

        now = timezone.now()

        self.dataset = Dataset.objects.create(name="test-ds", title="Test Dataset")
        self.other_dataset = Dataset.objects.create(name="other-ds", title="Other Dataset")

        self.recent = self._make_bin(
            "TEST_RECENT_BIN",
            now - timedelta(minutes=10),
            temperature=12.5,
            humidity=95.0,
        )
        self.older = self._make_bin(
            "TEST_OLDER_BIN",
            now - timedelta(days=2),
            temperature=20.1,
            humidity=80.0,
        )
        self.future = self._make_bin(
            "TEST_FUTURE_BIN",
            now + timedelta(days=1),
            temperature=30.0,
            humidity=10.0,
        )

        # all bins are in the test dataset; the future one is only in the "future" dataset
        self.recent.datasets.add(self.dataset)
        self.older.datasets.add(self.dataset)
        self.future.datasets.add(self.other_dataset)

    def _make_bin(self, pid, timestamp, temperature, humidity):
        return Bin.objects.create(
            pid=pid,
            timestamp=timestamp,
            sample_time=timestamp,
            temperature=temperature,
            humidity=humidity,
        )

    def test_most_recent_bin(self):
        response = self.client.get(
            "/most_recent_bin", query_params={"dataset": "test-ds"}
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["pid"], "TEST_RECENT_BIN")
        self.assertEqual(data["temperature"], 12.5)
        self.assertEqual(data["humidity"], 95.0)
        # the recent bin was sampled ~10 minutes ago
        self.assertAlmostEqual(data["time_since"], 600, delta=30)

    def test_unknown_dataset(self):
        response = self.client.get(
            "/most_recent_bin", query_params={"dataset": "no-such-ds"}
        )

        self.assertEqual(response.status_code, 404)

    def test_dataset_with_no_recent_bins(self):
        "Only the future (bad data) bin exists in this dataset, so nothing is valid"
        response = self.client.get(
            "/most_recent_bin", query_params={"dataset": "other-ds"}
        )

        self.assertEqual(response.status_code, 404)

    def test_missing_dataset_parameter(self):
        response = self.client.get("/most_recent_bin")

        # 422 from Ninja parameter validation, rather than the previous error
        self.assertEqual(response.status_code, 422)

    def test_api_key_auth_succeeds(self):
        response = self.client.get(
            "/most_recent_bin",
            query_params={"dataset": "test-ds"},
            headers={"X-API-Key": VALID_KEY},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pid"], "TEST_RECENT_BIN")

    def test_invalid_api_key_is_rejected(self):
        response = self.client.get(
            "/most_recent_bin",
            query_params={"dataset": "test-ds"},
            headers={"X-API-Key": "wrong-key"},
        )

        self.assertEqual(response.status_code, 401)
