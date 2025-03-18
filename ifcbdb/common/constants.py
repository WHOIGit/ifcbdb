from enum import Enum


# Values for this enum should map to their environment variable names
class Features(Enum):
    PRIVATE_DATASETS = "FEATURE_PRIVATE_DATASETS"
    USER_ROLES = "FEATURE_USER_ROLES"