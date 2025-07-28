from enum import Enum

class TeamRoles(Enum):
    CAPTAIN = 1
    MANAGER = 2
    USER = 3

# Values for this enum should map to their environment variable names
class Features(Enum):
    TEAMS = "Teams"
    PRIVATE_DATASETS = "PrivateDatasets"

