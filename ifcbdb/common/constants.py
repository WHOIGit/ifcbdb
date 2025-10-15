from enum import Enum

class TeamRoles(Enum):
    CAPTAIN = 1
    MANAGER = 2
    USER = 3

# Values for this enum should map to their environment variable names
class Features(Enum):
    TEAMS = "Teams"


class BinManagementActions(Enum):
    SKIP_BINS = "skip-bins"
    UNSKIP_BINS = "unskip-bins"
    ASSIGN_DATASET = "assign-dataset"
    UNASSIGN_DATASET = "unassign-dataset"

# Metadata column names
# TODO: More than just this one should be defined here (which is a duplicate of what's defined at the method level)
BIN_ID_COLUMNS = ['id','pid','lid','bin','bin_id','sample','sample_id','filename']