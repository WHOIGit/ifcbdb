from django.contrib.auth.models import User, Group

# At the moment, this is simply a wrapper around the superadmin flag. In the future, this, and possibly other
#   methods, will be used to determine access rules based on which teams a user is associated with and what
#   their assigned role is for that team
def is_admin(user):
    if not user.is_authenticated:
        return False

    return user.is_superuser
