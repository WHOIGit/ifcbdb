from common import auth as site_auth

from .principals import AnonymousPrincipal, UserPrincipal, is_api_key_principal
from .scopes import BIN_READ, BIN_SYNC


def is_admin(principal):
    if is_api_key_principal(principal):
        return False
    if isinstance(principal, UserPrincipal):
        return site_auth.is_admin(principal.user)
    return False


def can_manage_bins(principal):
    if is_api_key_principal(principal):
        return False
    if isinstance(principal, UserPrincipal):
        return site_auth.can_manage_bins(principal.user)
    return False


def can_update_bin(principal, bin):
    if is_api_key_principal(principal):
        return False
    if isinstance(principal, UserPrincipal):
        return site_auth.can_update_bin(principal.user, bin)
    return False


def can_read_bin(principal):
    "Read single bins via the bins:read scope for keys; session users and anonymous callers may read (legacy public reads)."
    if is_api_key_principal(principal):
        return principal.has_scope(BIN_READ)
    return True


def can_sync_bin(principal):
    "Sync single bins via the bins:sync scope for keys, capped by the owner's own permission; site users sync per is_admin; anonymous callers are allowed for legacy compatibility with the old unauthenticated endpoint."
    if isinstance(principal, AnonymousPrincipal):
        return True
    if is_api_key_principal(principal):
        return principal.has_scope(BIN_SYNC) and site_auth.is_admin(principal.user)
    if isinstance(principal, UserPrincipal):
        return site_auth.is_admin(principal.user)
    return False
