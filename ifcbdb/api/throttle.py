from django.conf import settings
from django.http import HttpRequest
from ninja.throttling import SimpleRateThrottle

from .principals import is_api_key_principal


class ApiKeyRateThrottle(SimpleRateThrottle):
    "Rolling-window throttle that only applies to API-key-authenticated requests."

    def __init__(self, rate=None):
        if rate is None:
            rate = f"{settings.API_KEY_THROTTLE_RATE}/min"
        super().__init__(rate=rate)

    def get_cache_key(self, request: HttpRequest):
        auth = getattr(request, "auth", None)
        if not is_api_key_principal(auth):
            return None

        return self.cache_format % {
            "scope": "api_key",
            "ident": auth.identity,
        }
