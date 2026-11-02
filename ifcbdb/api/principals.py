class UserPrincipal:
    is_authenticated = True
    is_api_key = False

    def __init__(self, user):
        self.user = user

    @property
    def identity(self):
        return self.user.username


class ApiKeyPrincipal:
    is_authenticated = True
    is_api_key = True

    # the API key is a standalone service identity: read-only access to all data
    read_only = True
    sees_all_data = True

    @property
    def identity(self):
        return "api-key"


class AnonymousPrincipal:
    is_authenticated = False
    is_api_key = False

    @property
    def identity(self):
        return "anonymous"


def is_user_principal(principal):
    return isinstance(principal, UserPrincipal)


def is_api_key_principal(principal):
    return isinstance(principal, ApiKeyPrincipal)
