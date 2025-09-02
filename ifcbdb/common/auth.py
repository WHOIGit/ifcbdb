from django.contrib.auth.models import User, Group
from dashboard.models import TeamUser
from .constants import TeamRoles

# At the moment, this is simply a wrapper around the superadmin flag. In the future, this, and possibly other
#   methods, will be used to determine access rules based on which teams a user is associated with and what
#   their assigned role is for that team
def is_admin(user):
    if not user.is_authenticated:
        return False

    return user.is_superuser

# This one is also just a wrapper around the staff flag. This is likely what will be used to determine if a user
#   has access to things "quickly" without having to check through associated teams and roles on those records
def is_staff(user):
    if not user.is_authenticated:
        return False

    if not user.is_staff:
        return False

    return user.is_staff


def can_manage_teams(user):
    if not user.is_authenticated:
        return False

    if user.is_superuser or user.is_staff:
        return True

    # Team captains have limited access to the admin to manage their own teams
    is_team_captain = TeamUser.objects \
        .filter(user=user) \
        .filter(role_id=TeamRoles.CAPTAIN.value) \
        .exists()
    if is_team_captain:
        return True

    return False

def can_access_settings(user):
    if not user.is_authenticated:
        return False
    
    if user.is_superuser or user.is_staff:
        return True

    if can_manage_teams(user):
        return True

    return False
