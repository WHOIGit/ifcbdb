from django.conf import settings
from .constants import Features


def is_feature_enabled(feature: Features) -> bool:
    return getattr(settings, feature.value, False)
