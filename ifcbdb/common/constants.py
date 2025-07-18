from enum import Enum

class RoleValues(Enum):
    ADMIN = "Admin"
    USER = "User"
    MANAGER = "Manager"

# Values for this enum should map to their environment variable names
class Features(Enum):
    TEAMS = "Teams"
