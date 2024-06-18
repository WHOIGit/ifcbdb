import base64
from django.contrib.auth.models import User
from ninja.security import HttpBearer


class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        try:
            username, password = base64.b64decode(token).decode('utf-8').split(':')

            user = User.objects.filter(username=username).first()
            if user is None:
                return False

            if not user.check_password(password):
                return False

            return user
        except Exception as e:
            return False

        return False
