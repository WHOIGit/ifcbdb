from django.conf import settings
from django.utils.crypto import constant_time_compare
from ninja.errors import AuthenticationError
from ninja.security import APIKeyCookie, APIKeyHeader, SessionAuth

from .principals import AnonymousPrincipal, ApiKeyPrincipal, UserPrincipal


class ApiKeyAuth(APIKeyHeader):
    """Standalone service-account key sent as the `X-API-Key` header.

    The key comes from the IFCB_API_KEY environment variable. An invalid
    key raises immediately (it never falls through to other authenticators).
    A blank/unset API_KEY disables key authentication.
    """

    param_name = "X-API-Key"

    def authenticate(self, request, key):
        if not key:
            return None

        expected = getattr(settings, "API_KEY", "")
        if not expected:
            raise AuthenticationError(message="API key authentication is not enabled")

        if constant_time_compare(key, expected):
            return ApiKeyPrincipal()

        raise AuthenticationError(message="Invalid API key")


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
