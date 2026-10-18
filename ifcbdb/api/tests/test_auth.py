from unittest.mock import Mock

from django.core.cache.backends.locmem import LocMemCache
from django.test import SimpleTestCase, override_settings
from ninja import NinjaAPI
from ninja.testing import TestClient

from api.auth import optional_auth, required_auth
from api.principals import AnonymousPrincipal, ApiKeyPrincipal, UserPrincipal
from api.throttle import ApiKeyRateThrottle

VALID_KEY = "a-valid-secret-key"


def make_user(authenticated=True, username="testuser", **flags):
    return Mock(username=username, is_authenticated=authenticated, **flags)


def build_api(throttle=None):
    api = NinjaAPI(title="test api", throttle=throttle)

    @api.get("/ping", auth=optional_auth())
    def ping(request):
        principal = request.auth
        return {
            "identity": principal.identity,
            "is_authenticated": principal.is_authenticated,
            "is_api_key": principal.is_api_key,
        }

    @api.get("/required", auth=required_auth())
    def required(request):
        return {"identity": request.auth.identity}

    @api.post("/echo", auth=optional_auth())
    def echo(request):
        return {"identity": request.auth.identity}

    return api


def client(**kwargs):
    return TestClient(build_api(), **kwargs)


@override_settings(API_KEY=VALID_KEY)
class OptionalAuthTests(SimpleTestCase):
    def setUp(self):
        self.c = client()

    def test_valid_api_key(self):
        r = self.c.get("/ping", headers={"X-API-Key": VALID_KEY})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["identity"], "api-key")
        self.assertTrue(j["is_authenticated"])
        self.assertTrue(j["is_api_key"])

    def test_invalid_api_key(self):
        r = self.c.get("/ping", headers={"X-API-Key": "wrong"})
        self.assertEqual(r.status_code, 401)

    def test_key_auth_disabled(self):
        with override_settings(API_KEY=""):
            r = TestClient(build_api()).get("/ping", headers={"X-API-Key": VALID_KEY})
        self.assertEqual(r.status_code, 401)
        self.assertIn("not enabled", r.json()["detail"])

    def test_anonymous_fallback(self):
        r = self.c.get("/ping")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["identity"], "anonymous")
        self.assertFalse(j["is_authenticated"])
        self.assertFalse(j["is_api_key"])

    def test_session_user(self):
        r = self.c.get("/ping", user=make_user())
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["identity"], "testuser")
        self.assertTrue(j["is_authenticated"])
        self.assertFalse(j["is_api_key"])


@override_settings(API_KEY=VALID_KEY)
class RequiredAuthTests(SimpleTestCase):
    def setUp(self):
        self.c = client()

    def test_anonymous_rejected(self):
        r = self.c.get("/required")
        self.assertEqual(r.status_code, 401)

    def test_api_key_accepted(self):
        r = self.c.get("/required", headers={"X-API-Key": VALID_KEY})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["identity"], "api-key")

    def test_session_user_accepted(self):
        r = self.c.get("/required", user=make_user())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["identity"], "testuser")


@override_settings(API_KEY=VALID_KEY)
class SessionAuthCsrfTests(SimpleTestCase):
    def test_csrf_enforced_on_unsafe_methods(self):
        api = build_api()
        c = TestClient(api)
        r = c.post(
            "/echo",
            user=make_user(),
            COOKIES={"sessionid": "sess"},
            _dont_enforce_csrf_checks=False,
        )
        self.assertEqual(r.status_code, 403)

    def test_csrf_not_enforced_on_safe_methods(self):
        api = build_api()
        c = TestClient(api, COOKIES={"sessionid": "sess"})
        r = c.get("/ping", user=make_user())
        self.assertEqual(r.status_code, 200)


@override_settings(API_KEY=VALID_KEY)
class ApiKeyThrottleTests(SimpleTestCase):
    def _request(self, api_key=True):
        from django.test import RequestFactory

        request = RequestFactory().get("/ping")
        request.auth = ApiKeyPrincipal() if api_key else AnonymousPrincipal()
        return request

    def test_throttles_api_key_requests(self):
        from django.test import RequestFactory

        throttle = ApiKeyRateThrottle(rate="3/min")
        throttle.cache = LocMemCache("throttle-test", {})
        request = RequestFactory().get("/ping")
        request.auth = ApiKeyPrincipal()
        for _ in range(3):
            self.assertTrue(throttle.allow_request(request))
        self.assertFalse(throttle.allow_request(request))
        self.assertLess(throttle.wait(), 61)

    def test_does_not_throttle_other_principals(self):
        from django.test import RequestFactory

        throttle = ApiKeyRateThrottle(rate="3/min")
        throttle.cache = LocMemCache("throttle-test", {})
        request = RequestFactory().get("/ping")
        request.auth = AnonymousPrincipal()
        for _ in range(50):
            self.assertTrue(throttle.allow_request(request))

    def test_api_key_exhausts_rate_end_to_end(self):
        throttle = ApiKeyRateThrottle(rate="3/min")
        throttle.cache = LocMemCache("throttle-e2e", {})
        c = TestClient(build_api(throttle=throttle))
        for _ in range(3):
            r = c.get("/ping", headers={"X-API-Key": VALID_KEY})
            self.assertEqual(r.status_code, 200)
        r = c.get("/ping", headers={"X-API-Key": VALID_KEY})
        self.assertEqual(r.status_code, 429)

    def test_anonymous_not_throttled_end_to_end(self):
        c = TestClient(build_api(throttle=ApiKeyRateThrottle(rate="3/min")))
        for _ in range(10):
            r = c.get("/ping")
            self.assertEqual(r.status_code, 200)


class PrincipalsTests(SimpleTestCase):
    def test_api_key_principal_flags(self):
        principal = ApiKeyPrincipal()
        self.assertTrue(principal.is_authenticated)
        self.assertTrue(principal.read_only)
        self.assertTrue(principal.sees_all_data)
        self.assertEqual(principal.identity, "api-key")

    def test_user_principal_flags(self):
        principal = UserPrincipal(make_user(username="captain"))
        self.assertTrue(principal.is_authenticated)
        self.assertFalse(principal.is_api_key)
        self.assertEqual(principal.identity, "captain")

    def test_anonymous_principal_flags(self):
        principal = AnonymousPrincipal()
        self.assertFalse(principal.is_authenticated)
        self.assertFalse(principal.is_api_key)
        self.assertEqual(principal.identity, "anonymous")
