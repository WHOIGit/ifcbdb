from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from ninja.testing import TestClient
from waffle.testutils import override_switch

from api.api import api
from api.models import ApiKey
from api.scopes import BIN_READ, BIN_SYNC
from dashboard.models import Bin, Dataset


def make_admin():
    return Mock(username="admin", is_authenticated=True, is_superuser=True)


def make_plain_user():
    return Mock(username="plain", is_authenticated=True, is_superuser=False)


@override_switch("DashboardApi", active=True)
class SyncBinEndpointTests(TestCase):
    "GET /api/sync_bin"

    def setUp(self):
        self.client = TestClient(api)

        self.dataset = Dataset.objects.create(name="test-ds", title="Test Dataset")

        self.admin = User.objects.create_user("admin", password="pw", is_superuser=True)
        self.plain = User.objects.create_user("plain", password="pw")

        self.sync_key, _ = ApiKey.objects.create_key(
            user=self.admin, name="sync key", scopes=[BIN_SYNC]
        )
        self.read_key, _ = ApiKey.objects.create_key(
            user=self.admin, name="read key", scopes=[BIN_READ]
        )
        self.plains_sync_key, _ = ApiKey.objects.create_key(
            user=self.plain, name="plain sync key", scopes=[BIN_SYNC]
        )

    def _make_bin(self, pid):
        now = timezone.now()
        return Bin.objects.create(
            pid=pid,
            timestamp=now - timedelta(minutes=10),
            sample_time=now,
            temperature=12.5,
            humidity=95.0,
        )

    @patch("api.routers.bins.Accession")
    def test_syncs_new_bin_with_admin_session(self, accession):
        accession.return_value.sync_one.return_value = Mock()

        r = self.client.get(
            "/sync_bin",
            query_params={"dataset": "test-ds", "bin": "NEW_BIN"},
            user=make_admin(),
        )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result"], "synced")
        accession.assert_called_once()
        accession.return_value.sync_one.assert_called_once_with("NEW_BIN")

    @patch("api.routers.bins.Accession")
    def test_syncs_new_bin_with_scoped_api_key(self, accession):
        accession.return_value.sync_one.return_value = Mock()

        r = self.client.get(
            "/sync_bin",
            query_params={"dataset": "test-ds", "bin": "NEW_BIN"},
            headers={"X-API-Key": self.sync_key},
        )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result"], "synced")

    def test_exists_when_bin_already_ingested(self):
        self._make_bin("EXISTING_BIN")

        with patch("api.routers.bins.Accession") as accession:
            r = self.client.get(
                "/sync_bin",
                query_params={"dataset": "test-ds", "bin": "EXISTING_BIN"},
                headers={"X-API-Key": self.sync_key},
            )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result"], "exists")
        accession.assert_not_called()

    @patch("api.routers.bins.Accession")
    def test_anonymous_allowed_for_legacy_compatibility(self, accession):
        "the old endpoint allowed unauthenticated callers; keep that behavior"
        accession.return_value.sync_one.return_value = Mock()

        r = self.client.get(
            "/sync_bin", query_params={"dataset": "test-ds", "bin": "NEW_BIN"}
        )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result"], "synced")

    def test_key_without_sync_scope_forbidden(self):
        r = self.client.get(
            "/sync_bin",
            query_params={"dataset": "test-ds", "bin": "NEW_BIN"},
            headers={"X-API-Key": self.read_key},
        )
        self.assertEqual(r.status_code, 403)

    def test_non_admin_session_user_forbidden(self):
        r = self.client.get(
            "/sync_bin",
            query_params={"dataset": "test-ds", "bin": "NEW_BIN"},
            user=make_plain_user(),
        )
        self.assertEqual(r.status_code, 403)

    def test_scope_capped_by_non_admin_owner(self):
        "a non-admin's key has the scope but is denied anyway"
        r = self.client.get(
            "/sync_bin",
            query_params={"dataset": "test-ds", "bin": "NEW_BIN"},
            headers={"X-API-Key": self.plains_sync_key},
        )
        self.assertEqual(r.status_code, 403)

    def test_unknown_dataset(self):
        r = self.client.get(
            "/sync_bin",
            query_params={"dataset": "no-such-ds", "bin": "NEW_BIN"},
            headers={"X-API-Key": self.sync_key},
        )
        self.assertEqual(r.status_code, 404)

    @patch("api.routers.bins.Accession")
    def test_bin_not_found_in_data_dirs(self, accession):
        accession.return_value.sync_one.return_value = None

        r = self.client.get(
            "/sync_bin",
            query_params={"dataset": "test-ds", "bin": "MISSING_BIN"},
            headers={"X-API-Key": self.sync_key},
        )
        self.assertEqual(r.status_code, 404)

    def test_missing_bin_parameter(self):
        "422 from Ninja parameter validation"
        r = self.client.get(
            "/sync_bin",
            query_params={"dataset": "test-ds"},
            headers={"X-API-Key": self.sync_key},
        )
        self.assertEqual(r.status_code, 422)

    def test_missing_dataset_parameter(self):
        r = self.client.get(
            "/sync_bin",
            query_params={"bin": "NEW_BIN"},
            headers={"X-API-Key": self.sync_key},
        )
        self.assertEqual(r.status_code, 422)
