from django.contrib.auth.decorators import login_required
import waffle
from ninja import NinjaAPI
from waffle.decorators import waffle_switch

from common.constants import Features

from .routers.bins import router as bins_router
from .routers.meta import router as meta_router
from .throttle import ApiKeyRateThrottle


def _gated_docs(view):
    "The API docs are available to logged-in users while the DashboardApi switch is on."

    @login_required
    @waffle_switch(Features.DASHBOARD_API.value)
    def wrapper(request, *args, **kwargs):
        return view(request, *args, **kwargs)

    return wrapper


api = NinjaAPI(
    title="IFCB Dashboard API",
    version="1.0.0",
    description=(
        "REST API for IFCB Dashboard bin, image and dataset data. "
        "Authenticated with a Django session (browser) or a per-user API key "
        "sent as the `X-API-Key` header (generate one from the dashboard's "
        "API Keys page; each key carries scopes that are enforced per endpoint)."
    ),
    docs_decorator=_gated_docs,
    throttle=ApiKeyRateThrottle(),
)

api.add_router("", meta_router)
api.add_router("", bins_router)
