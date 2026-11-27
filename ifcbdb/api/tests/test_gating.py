from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from ninja import NinjaAPI
from ninja.testing import TestClient
from waffle.testutils import override_switch

from api.api import api
from api.auth import required_auth
from api.models import ApiKey
from api.scopes import BIN_READ
from dashboard.models import Bin, Dataset


class ApiKeySwitchGatingTests(TestCase):
    "API-key authentication is disabled while the DashboardApi switch is off."

    def setUp(self):
        self.c = TestClient(api)
        user = User.objects.create_user("keyuser", password="pw")
        self.raw_key, _ = ApiKey.objects.create_key(
            user=user, name="test key", scopes=[BIN_READ]
        )

    @override_switch("DashboardApi", active=False)
    def test_switch_off_valid_key_is_rejected(self):
        "sending an API key while the feature is off fails (401)"
        r = self.c.get("/ping", headers={"X-API-Key": self.raw_key})

        self.assertEqual(r.status_code, 401)

    @override_switch("DashboardApi", active=False)
    def test_switch_off_invalid_key_is_rejected(self):
        r = self.c.get("/ping", headers={"X-API-Key": "no-such-key"})

        self.assertEqual(r.status_code, 401)

    @override_switch("DashboardApi", active=False)
    def test_switch_off_no_key_still_public(self):
        "without a key, the endpoints stay public (legacy behavior)"
        r = self.c.get("/ping")

        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["identity"], "anonymous")
        self.assertFalse(j["is_api_key"])

    @override_switch("DashboardApi", active=False)
    def test_switch_off_no_key_most_recent_bin_still_public(self):
        "the legacy-public bin endpoints keep working without a key"
        now = timezone.now()
        dataset = Dataset.objects.create(name="gated-ds", title="Gated Dataset")
        bin_ = Bin.objects.create(
            pid="GATED_BIN",
            timestamp=now - timedelta(minutes=10),
            sample_time=now,
            temperature=12.5,
            humidity=95.0,
        )
        bin_.datasets.add(dataset)

        r = self.c.get("/most_recent_bin", query_params={"dataset": "gated-ds"})

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pid"], "GATED_BIN")

    @override_switch("DashboardApi", active=False)
    def test_switch_off_key_rejected_on_required_endpoint(self):
        "endpoints that require authentication reject key callers with 401"
        test_api = NinjaAPI(title="gating test api")

        @test_api.get("/required", auth=required_auth())
        def required(request):
            return {"identity": request.auth.identity}

        r = TestClient(test_api).get("/required", headers={"X-API-Key": self.raw_key})

        self.assertEqual(r.status_code, 401)

    @override_switch("DashboardApi", active=True)
    def test_switch_on_valid_key_authenticates(self):
        r = self.c.get("/ping", headers={"X-API-Key": self.raw_key})

        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j["authenticated"])
        self.assertTrue(j["is_api_key"])


class DocsGatingTests(TestCase):
    "The OpenAPI docs endpoints (/api/docs, /api/openapi.json) follow the switch."

    @override_switch("DashboardApi", active=False)
    def test_docs_404_when_switch_off(self):
        user = User.objects.create_user("docsuser", password="pw")
        self.client.force_login(user)

        self.assertEqual(self.client.get("/api/docs").status_code, 404)
        self.assertEqual(self.client.get("/api/openapi.json").status_code, 404)

    @override_switch("DashboardApi", active=False)
    def test_anonymous_docs_redirect_to_login_when_switch_off(self):
        r = self.client.get("/api/docs")

        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r.url)

    @override_switch("DashboardApi", active=True)
    def test_docs_require_login_when_switch_on(self):
        r = self.client.get("/api/docs")

        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r.url)

    @override_switch("DashboardApi", active=True)
    def test_docs_render_when_switch_on(self):
        user = User.objects.create_user("docsuser2", password="pw")
        self.client.force_login(user)

        self.assertEqual(self.client.get("/api/docs").status_code, 200)
        self.assertEqual(self.client.get("/api/openapi.json").status_code, 200)
