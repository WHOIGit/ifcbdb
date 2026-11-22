from .scopes import scopes_allow


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

    # an API key acts as its owning user, with read-only access to public
    # data plus whatever extra scopes were granted at creation time; what a
    # scope allows is additionally capped by the owner's own permissions
    read_only = True
    sees_all_data = False

    def __init__(self, api_key):
        self.api_key = api_key
        self.user = api_key.user

    @property
    def identity(self):
        return f"api-key:{self.user.get_username()}:{self.api_key.name}"

    def has_scope(self, scope):
        return scopes_allow(self.api_key.scopes, scope)


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
