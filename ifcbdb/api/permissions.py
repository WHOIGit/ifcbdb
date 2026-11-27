from common import auth as site_auth

from .principals import is_anonymous_principal, is_api_key_principal, is_user_principal
from .scopes import BIN_READ, BIN_SYNC


def is_admin(principal):
    if is_api_key_principal(principal):
        return False
    if is_user_principal(principal):
        return site_auth.is_admin(principal.user)
    return False


def can_manage_bins(principal):
    if is_api_key_principal(principal):
        return False
    if is_user_principal(principal):
        return site_auth.can_manage_bins(principal.user)
    return False


def can_update_bin(principal, bin):
    if is_api_key_principal(principal):
        return False
    if is_user_principal(principal):
        return site_auth.can_update_bin(principal.user, bin)
    return False


def can_read_bin(principal):
    """
    Read single bins via the bins:read scope for keys; session users and anonymous callers may read (legacy public
    reads).
    """

    # If auth is using an API key, require the bins:read scope
    if is_api_key_principal(principal):
        return principal.has_scope(BIN_READ)

    # Access is "open" to retain backwards compatibility with legacy consumers
    return is_anonymous_principal(principal) or is_user_principal(principal)


def can_sync_bin(principal):
    """
    Sync single bins via the bins:sync scope for keys, capped by the owner's own permission; session users and anonymous
    callers are allowed for legacy compatibility with the old unauthenticated endpoint.
    """

    # If auth is using API key, require bins:sync scope and admin role
    if is_api_key_principal(principal):
        return principal.has_scope(BIN_SYNC) and site_auth.is_admin(principal.user)

    # Access is "open" to retain backwards compatibility with legacy consumers
    return is_anonymous_principal(principal) or is_user_principal(principal)
