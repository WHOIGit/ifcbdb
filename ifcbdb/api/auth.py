from django.conf import settings

import waffle
from ninja.errors import AuthenticationError
from ninja.security import APIKeyCookie, APIKeyHeader, SessionAuth

from common.constants import Features

from .models import ApiKey
from .principals import AnonymousPrincipal, ApiKeyPrincipal, UserPrincipal


class ApiKeyAuth(APIKeyHeader):
    """Per-user API key sent as the `X-API-Key` header.

    Keys are generated and managed by each user from the dashboard's
    "API Keys" page and stored hashed. An unknown, malformed, revoked,
    expired key (or a key whose owner is inactive) raises immediately:
    it never falls through to other authenticators.

    The feature is gated behind the `DashboardApi` waffle switch: while
    the switch is off, API-key authentication is unsupported entirely and
    any presented key is rejected (requests without a key are unaffected:
    session users and anonymous callers carry on as before).
    """

    param_name = "X-API-Key"

    def authenticate(self, request, key):
        if not key:
            return None

        if not waffle.switch_is_active(Features.DASHBOARD_API.value):
            # the API key feature is disabled: keys are not supported at all,
            #   so a presented key fails rather than silently degrading. A
            #   request without a key never reaches this check and keeps
            #   working via the next authenticators (public endpoints).
            raise AuthenticationError(message="API key authentication is disabled")

        api_key = ApiKey.objects.authenticate(key)
        if api_key is None:
            raise AuthenticationError(message="Invalid API key")

        return ApiKeyPrincipal(api_key)


class DjangoSessionAuth(SessionAuth):
    """Django session-cookie authentication (existing `secure:login` users).

    Cookie-based, so Ninja enforces CSRF for unsafe methods, accepting the
    `X-CSRFToken` header or the `csrfmiddlewaretoken` form field.
    """

    def authenticate(self, request, key):
        if request.user.is_authenticated:
            return UserPrincipal(request.user)
        return None


class OptionalAnonymousAuth(APIKeyCookie):
    """Final fallback authenticator: no credentials -> AnonymousPrincipal.

    Cookie-based (reads the session cookie) so that CSRF is still enforced
    for unsafe requests even when the caller is anonymous, mirroring the
    behavior of the legacy views protected by Django's middleware. The
    preceding authenticators raise on invalid credentials rather than
    falling through, so senders of a bad API key get a 401.
    """

    param_name = settings.SESSION_COOKIE_NAME

    def authenticate(self, request, key):
        return AnonymousPrincipal()


def required_auth():
    "Auth chain: API key or logged-in user; otherwise 401."
    return [ApiKeyAuth(), DjangoSessionAuth()]


def optional_auth():
    "Auth chain: API key, logged-in user, or anonymous (public reads)."
    return [ApiKeyAuth(), DjangoSessionAuth(), OptionalAnonymousAuth()]
