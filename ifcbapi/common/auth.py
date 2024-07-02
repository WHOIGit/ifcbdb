from rest_framework.authtoken.models import Token
from ninja.security import HttpBearer


class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        try:
            token_object = Token.objects.filter(pk=token).first()
            if token_object is None or token_object.user is None:
                return False

            return(token_object.user)

        except Exception as e:
            return False

        return False

