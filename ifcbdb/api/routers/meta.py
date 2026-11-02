from ninja import Router, Schema

from ..auth import optional_auth

router = Router(tags=["Meta"])


class PingResponse(Schema):
    status: str
    api_version: str
    authenticated: bool
    identity: str
    is_api_key: bool


@router.get(
    "/ping",
    auth=optional_auth(),
    response=PingResponse,
    summary="Health check / auth echo",
    description=(
        "Verifies the API is up and reports how the caller was authenticated "
        "(anonymous, Django session user, or API-key service account)."
    ),
)
def ping(request):
    principal = request.auth
    from .. import api

    return {
        "status": "ok",
        "api_version": api.api.version,
        "authenticated": principal.is_authenticated,
        "identity": principal.identity,
        "is_api_key": principal.is_api_key,
    }
