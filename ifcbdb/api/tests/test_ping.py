import json
from unittest.mock import Mock

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from ninja.testing import TestClient
from waffle.testutils import override_switch

from api.api import api
from api.models import ApiKey
from api.scopes import BIN_READ


@override_switch("DashboardApi", active=True)
class OpenApiSpecTests(TestCase):
    def _spec(self):
        request = RequestFactory().get("/api/openapi.json")
        request.user = Mock(is_authenticated=True)
        response = TestClient(api).request(
            "GET",
            "/openapi.json",
            user=request.user,
            _dont_enforce_csrf_checks=True,
        )
        return json.loads(response.content)

    def test_ping_in_openapi_spec(self):
        spec = self._spec()
        self.assertIn("/api/ping", spec["paths"])
        op = spec["paths"]["/api/ping"]["get"]
        self.assertIn("ApiKeyAuth", [k for scheme in op["security"] for k in scheme])

    def test_most_recent_bin_in_openapi_spec(self):
        spec = self._spec()
        self.assertIn("/api/most_recent_bin", spec["paths"])
        op = spec["paths"]["/api/most_recent_bin"]["get"]
        self.assertIn("ApiKeyAuth", [k for scheme in op["security"] for k in scheme])
        # the response schema is documented, not just inferred
        self.assertEqual(
            op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/MostRecentBinResponse",
        )

    def test_spec_metadata(self):
        spec = self._spec()
        self.assertEqual(spec["info"]["title"], "IFCB Dashboard API")
        self.assertEqual(spec["info"]["version"], "1.0.0")


@override_switch("DashboardApi", active=True)
class PingEndpointTests(TestCase):
    def setUp(self):
        self.client = TestClient(api)
        user = User.objects.create_user("keyuser", password="pw")
        self.raw_key, _ = ApiKey.objects.create_key(
            user=user, name="test key", scopes=[BIN_READ]
        )

    def test_anonymous_ping(self):
        r = self.client.get("/ping")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["status"], "ok")
        self.assertFalse(j["authenticated"])
        self.assertEqual(j["identity"], "anonymous")
        self.assertFalse(j["is_api_key"])
        self.assertEqual(j["api_version"], api.version)

    def test_ping_with_api_key(self):
        r = self.client.get("/ping", headers={"X-API-Key": self.raw_key})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j["authenticated"])
        self.assertTrue(j["identity"].startswith("api-key:"))
        self.assertTrue(j["is_api_key"])

    def test_ping_with_invalid_api_key(self):
        r = self.client.get("/ping", headers={"X-API-Key": "wrong"})
        self.assertEqual(r.status_code, 401)

    def test_ping_with_session_user(self):
        user = Mock(username="reviewer", is_authenticated=True)
        r = self.client.get("/ping", user=user)
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j["authenticated"])
        self.assertEqual(j["identity"], "reviewer")
        self.assertFalse(j["is_api_key"])
