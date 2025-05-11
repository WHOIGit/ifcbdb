from django.contrib.auth.models import User, Group
from .constants import RoleValues

def is_admin(user):
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if not user.groups:
        return False

    return user.groups.filter(name=RoleValues.ADMIN.value).exists()

def is_manager_or_admin(user):
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if not user.groups:
        return False

    return user.groups.filter(name__in=[RoleValues.ADMIN.value, RoleValues.MANAGER.value]).exists()