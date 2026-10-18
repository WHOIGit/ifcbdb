from datetime import datetime

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema

from dashboard.models import Bin, Dataset

from ..auth import optional_auth

router = Router(tags=["Bins"])


class MostRecentBinResponse(Schema):
    pid: str
    timestamp: datetime
    time_since: int
    temperature: float
    humidity: float


@router.get(
    "/most_recent_bin",
    auth=optional_auth(),
    response=MostRecentBinResponse,
    url_name="most_recent_bin",
    summary="Most recent bin in a dataset",
    description=(
        "Returns the PID, timestamp, and environmental readings of the most "
        "recently sampled bin in a dataset. Bins with a timestamp in the "
        "future are excluded, since that usually indicates bad data. "
    ),
)
def most_recent_bin(request, dataset: str):
    # 404s if the dataset doesn't exist
    _ = get_object_or_404(Dataset, name=dataset)

    # The most recent bin is based on the bin's timestamp. Bins that have a timestamp in the future are excluded
    #   because it's usually indicative of bad data
    bin = Bin.objects \
        .filter(datasets__name=dataset) \
        .exclude(timestamp__gt=timezone.now()) \
        .order_by("-timestamp") \
        .first()

    if not bin:
        raise Http404("Dataset has no bins")

    return {
        "pid": bin.pid,
        "timestamp": bin.timestamp,
        "time_since": round((timezone.now() - bin.timestamp).total_seconds()),
        "temperature": bin.temperature,
        "humidity": bin.humidity,
    }
