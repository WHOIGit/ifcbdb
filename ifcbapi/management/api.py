from django.http import HttpRequest, JsonResponse
from ninja import Router
from common.auth import AuthBearer


router = Router()


@router.post("/update/", auth=AuthBearer())
def update(request: HttpRequest):
    user = request.auth

    return JsonResponse({
        'success': True,
        'username': user.username,
    })
