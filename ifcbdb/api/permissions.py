from common import auth as site_auth

from .principals import UserPrincipal, is_api_key_principal


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
