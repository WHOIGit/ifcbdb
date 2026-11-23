from datetime import timedelta
from unittest.mock import Mock

from django.contrib.auth.models import User
from django.core.cache.backends.locmem import LocMemCache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from ninja import NinjaAPI
from ninja.testing import TestClient
from waffle.testutils import override_switch

from api.auth import optional_auth, required_auth
from api.models import ApiKey
from api.principals import AnonymousPrincipal, ApiKeyPrincipal, UserPrincipal
from api.scopes import BIN_READ, BIN_SYNC, scopes_allow
from api.throttle import ApiKeyRateThrottle


def make_user(authenticated=True, username="testuser", **flags):
    return Mock(username=username, is_authenticated=authenticated, **flags)


def make_owner(username="keyowner", is_superuser=False):
    "An unsaved User, for no-database tests that need a key owner."
    return User(username=username, is_superuser=is_superuser, is_active=True)


def make_key(prefix="abcd1234", scopes=None, name="test key", **kwargs):
    "An unsaved ApiKey, for principal-level tests that need no database."
    kwargs.setdefault("user", make_owner())
    return ApiKey(
        prefix=prefix, scopes=BIN_READ if scopes is None else scopes, name=name, **kwargs
    )


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


class OptionalAuthTests(SimpleTestCase):
    def setUp(self):
        self.c = client()

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

    def test_empty_key_header_falls_through(self):
        r = self.c.get("/ping", headers={"X-API-Key": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["identity"], "anonymous")


class RequiredAuthTests(SimpleTestCase):
    def setUp(self):
        self.c = client()

    def test_anonymous_rejected(self):
        r = self.c.get("/required")
        self.assertEqual(r.status_code, 401)

    def test_session_user_accepted(self):
        r = self.c.get("/required", user=make_user())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["identity"], "testuser")


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


@override_switch("DashboardApi", active=True)
class ApiKeyAuthTests(TestCase):
    "API-key authentication against real (hashed, per-user) keys."

    def setUp(self):
        self.c = client()
        self.user = User.objects.create_user("keyuser", password="pw")
        self.raw_key, self.api_key = ApiKey.objects.create_key(
            user=self.user, name="test key", scopes=[BIN_READ]
        )

    def test_valid_api_key(self):
        r = self.c.get("/ping", headers={"X-API-Key": self.raw_key})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(
            j["identity"], f"api-key:{self.user.username}:{self.api_key.name}"
        )
        self.assertTrue(j["is_authenticated"])
        self.assertTrue(j["is_api_key"])

    def test_key_accepted_on_required_endpoint(self):
        r = self.c.get("/required", headers={"X-API-Key": self.raw_key})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json()["identity"], f"api-key:{self.user.username}:{self.api_key.name}"
        )

    def test_invalid_api_key(self):
        r = self.c.get("/ping", headers={"X-API-Key": "wrong"})
        self.assertEqual(r.status_code, 401)

    def test_malformed_api_key(self):
        r = self.c.get("/ping", headers={"X-API-Key": "no-dot-in-me"})
        self.assertEqual(r.status_code, 401)

    def test_revoked_api_key(self):
        self.api_key.revoked = True
        self.api_key.save(update_fields=["revoked"])

        r = self.c.get("/ping", headers={"X-API-Key": self.raw_key})
        self.assertEqual(r.status_code, 401)

    def test_expired_api_key(self):
        self.api_key.expires_at = timezone.now() - timedelta(days=1)
        self.api_key.save(update_fields=["expires_at"])

        r = self.c.get("/ping", headers={"X-API-Key": self.raw_key})
        self.assertEqual(r.status_code, 401)

    def test_inactive_owner_rejected(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        r = self.c.get("/ping", headers={"X-API-Key": self.raw_key})
        self.assertEqual(r.status_code, 401)

    def test_tampered_secret_rejected(self):
        prefix, _, _ = self.raw_key.partition(".")
        r = self.c.get("/ping", headers={"X-API-Key": f"{prefix}.forged-secret"})
        self.assertEqual(r.status_code, 401)

    def test_last_used_recorded(self):
        self.assertIsNone(self.api_key.last_used_at)
        self.c.get("/ping", headers={"X-API-Key": self.raw_key})
        self.api_key.refresh_from_db()
        self.assertIsNotNone(self.api_key.last_used_at)


class ApiKeyModelTests(TestCase):
    def test_create_key_shows_raw_once(self):
        user = User.objects.create_user("modeluser", password="pw")
        raw_key, api_key = ApiKey.objects.create_key(
            user=user, name="k", scopes=[BIN_READ]
        )

        self.assertTrue(raw_key.startswith("ifcb_"))
        self.assertIn(".", raw_key)
        self.assertNotIn(raw_key, api_key.hashed_key)  # only the hash is stored
        self.assertEqual(api_key.user, user)
        self.assertEqual(api_key.scopes, [BIN_READ])
        self.assertTrue(api_key.is_valid)

    def test_authenticate_round_trip(self):
        user = User.objects.create_user("modeluser2", password="pw")
        raw_key, api_key = ApiKey.objects.create_key(
            user=user, name="k", scopes=[BIN_READ]
        )
        found = ApiKey.objects.authenticate(raw_key)
        self.assertEqual(found.pk, api_key.pk)

    def test_authenticate_rejects_unknown_prefix(self):
        self.assertIsNone(ApiKey.objects.authenticate("zzzzzzzz.somesecret"))

    def test_authenticate_rejects_garbage(self):
        self.assertIsNone(ApiKey.objects.authenticate(""))
        self.assertIsNone(ApiKey.objects.authenticate("no-dot"))
        self.assertIsNone(ApiKey.objects.authenticate(None))


class ApiKeyThrottleTests(SimpleTestCase):
    def _throttle(self, cache_name="throttle-test"):
        throttle = ApiKeyRateThrottle(rate="3/min")
        throttle.cache = LocMemCache(cache_name, {})
        return throttle

    def _request(self, principal):
        from django.test import RequestFactory

        request = RequestFactory().get("/ping")
        request.auth = principal
        return request

    def test_throttles_api_key_requests_per_key(self):
        throttle = self._throttle("throttle-per-key")
        principal = ApiKeyPrincipal(make_key(prefix="aaaa1111"))
        request = self._request(principal)
        for _ in range(3):
            self.assertTrue(throttle.allow_request(request))
        self.assertFalse(throttle.allow_request(request))
        self.assertLess(throttle.wait(), 61)

    def test_each_key_throttled_independently(self):
        throttle = self._throttle("throttle-independence")
        first = self._request(ApiKeyPrincipal(make_key(prefix="aaaa1111")))
        second = self._request(ApiKeyPrincipal(make_key(prefix="bbbb2222")))
        for _ in range(3):
            self.assertTrue(throttle.allow_request(first))
        # the second key has its own bucket
        self.assertTrue(throttle.allow_request(second))

    def test_does_not_throttle_other_principals(self):
        throttle = self._throttle()
        request = self._request(AnonymousPrincipal())
        for _ in range(50):
            self.assertTrue(throttle.allow_request(request))


class PrincipalsTests(SimpleTestCase):
    def test_api_key_principal_flags(self):
        principal = ApiKeyPrincipal(make_key(prefix="abcd1234", scopes=[BIN_READ]))
        self.assertTrue(principal.is_authenticated)
        self.assertTrue(principal.is_api_key)
        self.assertTrue(principal.read_only)
        self.assertFalse(principal.sees_all_data)
        self.assertEqual(principal.identity, "api-key:keyowner:test key")

    def test_api_key_principal_scopes(self):
        principal = ApiKeyPrincipal(make_key(prefix="abcd1234", scopes=[BIN_READ]))
        self.assertTrue(principal.has_scope(BIN_READ))
        self.assertFalse(principal.has_scope(BIN_SYNC))

    def test_api_key_principal_wildcard_scopes(self):
        principal = ApiKeyPrincipal(make_key(prefix="abcd1234", scopes=["bins:*"]))
        self.assertTrue(principal.has_scope(BIN_READ))
        self.assertTrue(principal.has_scope(BIN_SYNC))

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


class ScopesTests(SimpleTestCase):
    def test_exact_match(self):
        self.assertTrue(scopes_allow([BIN_READ], BIN_READ))
        self.assertFalse(scopes_allow([BIN_READ], BIN_SYNC))

    def test_namespace_wildcard(self):
        self.assertTrue(scopes_allow(["bins:*"], BIN_READ))
        self.assertTrue(scopes_allow(["bins:*"], BIN_SYNC))
        self.assertFalse(scopes_allow(["bins:*"], "other:read"))

    def test_global_wildcard(self):
        self.assertTrue(scopes_allow(["*"], BIN_SYNC))

    def test_bare_namespace_does_not_match(self):
        self.assertFalse(scopes_allow(["bins"], BIN_READ))


class PermissionScopeTests(SimpleTestCase):
    "Effective access for a key is its scope capped by the owner's own permissions."

    def _key_principal(self, scopes, owner_flags):
        owner = make_owner(is_superuser=owner_flags)
        return ApiKeyPrincipal(make_key(scopes=scopes, user=owner))

    def test_sync_scope_with_admin_owner_allowed(self):
        from api import permissions

        principal = self._key_principal([BIN_SYNC], owner_flags=True)
        self.assertTrue(permissions.can_sync_bin(principal))

    def test_sync_scope_with_non_admin_owner_denied(self):
        from api import permissions

        principal = self._key_principal([BIN_SYNC], owner_flags=False)
        self.assertFalse(permissions.can_sync_bin(principal))

    def test_read_scope_allowed(self):
        from api import permissions

        principal = self._key_principal([BIN_READ], owner_flags=False)
        self.assertTrue(permissions.can_read_bin(principal))

    def test_read_scope_missing_denied(self):
        from api import permissions

        principal = self._key_principal([BIN_SYNC], owner_flags=True)
        self.assertFalse(permissions.can_read_bin(principal))

    def test_anonymous_allowed_for_legacy_endpoints(self):
        from api import permissions

        principal = AnonymousPrincipal()
        self.assertTrue(permissions.can_read_bin(principal))
        self.assertTrue(permissions.can_sync_bin(principal))

    def test_sync_scope_missing_denied_even_for_admin_owner(self):
        from api import permissions

        principal = self._key_principal([BIN_READ], owner_flags=True)
        self.assertFalse(permissions.can_sync_bin(principal))

    def test_key_principal_denied_write_permissions(self):
        from api import permissions

        principal = self._key_principal([BIN_SYNC], owner_flags=True)
        self.assertFalse(permissions.is_admin(principal))
        self.assertFalse(permissions.can_manage_bins(principal))


@override_switch("DashboardApi", active=True)
class ApiKeyThrottleEndToEndTests(TestCase):
    "Throttle tests that need database-backed keys."

    def test_api_key_exhausts_rate_end_to_end(self):
        user = User.objects.create_user("throttleuser", password="pw")
        raw_key, _ = ApiKey.objects.create_key(
            user=user, name="k", scopes=[BIN_READ]
        )
        throttle = ApiKeyRateThrottle(rate="3/min")
        throttle.cache = LocMemCache("throttle-e2e", {})
        c = TestClient(build_api(throttle=throttle))
        for _ in range(3):
            r = c.get("/ping", headers={"X-API-Key": raw_key})
            self.assertEqual(r.status_code, 200)
        r = c.get("/ping", headers={"X-API-Key": raw_key})
        self.assertEqual(r.status_code, 429)

    def test_anonymous_not_throttled_end_to_end(self):
        c = TestClient(build_api(throttle=ApiKeyRateThrottle(rate="3/min")))
        for _ in range(10):
            r = c.get("/ping")
            self.assertEqual(r.status_code, 200)
