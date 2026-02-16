from django.contrib.auth.models import User, Group
from dashboard.models import Dataset, Team, TeamDataset, TeamUser
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


# This is a wrapper for checking on whether the user has full access to bins, datasets without the need to be associated
#   with them as either a captain or team
def has_admin_access(user):
    if not user.is_authenticated:
        return False

    return user.is_superuser or user.is_staff

def can_manage_teams(user):
    if not user.is_authenticated:
        return False

    if user.is_superuser or user.is_staff:
        return True

    # Team captains have limited access to the admin to manage their own teams
    return has_team_roles(user, [TeamRoles.CAPTAIN, ])

def can_manage_datasets(user):
    if not user.is_authenticated:
        return False

    if user.is_superuser or user.is_staff:
        return True

    # Team captains have limited access to the admin to manage their own datasets
    return has_team_roles(user, [TeamRoles.CAPTAIN, ])

def can_manage_metadata(user):
    if not user.is_authenticated:
        return False

    if user.is_superuser or user.is_staff:
        return True

    # Team captains have limited access to the admin to manage their own metadata
    return has_team_roles(user, [TeamRoles.CAPTAIN, ])

def can_manage_bins(user):
    if not user.is_authenticated:
        return False

    if user.is_superuser or user.is_staff:
        return True

    # Team captains and managers have limited access to the admin to manage their own bins
    return has_team_roles(user, [TeamRoles.CAPTAIN, TeamRoles.MANAGER, ])

def can_access_settings(user):
    if not user.is_authenticated:
        return False

    if user.is_superuser or user.is_staff:
        return True

    return has_team_roles(user, [TeamRoles.CAPTAIN, TeamRoles.MANAGER ])

def has_team_roles(user, roles):
    role_values = [role.value for role in roles]

    return TeamUser.objects \
        .filter(user=user) \
        .filter(role_id__in=role_values) \
        .exists()

def get_manageable_teams(user):
    if not user.is_authenticated:
        return []

    if user.is_superuser or user.is_staff:
        return Team.objects.all()

    return Team.objects \
        .filter(teamuser__user=user, teamuser__role_id__in=[TeamRoles.CAPTAIN.value, ]) \
        .distinct()

def get_manageable_datasets(user, exclude_inactive=True):
    if not user.is_authenticated:
        return []

    datasets = Dataset.objects.all()

    if exclude_inactive:
        datasets = datasets.exclude(is_active=False)

    if user.is_superuser or user.is_staff:
        return datasets

    teams = get_manageable_teams(user)

    dataset_ids = TeamDataset.objects \
        .filter(team__in=teams) \
        .values_list("dataset_id", flat=True)

    return datasets.filter(id__in=dataset_ids)
