from datetime import datetime

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from dashboard.accession import Accession
from dashboard.models import Bin, Dataset

from ..auth import optional_auth
from ..permissions import can_read_bin, can_sync_bin

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
        "Requires the `bins:read` scope (API keys); session users and "
        "anonymous callers are accepted for legacy compatibility."
    ),
)
def most_recent_bin(request, dataset: str):
    if not can_read_bin(request.auth):
        raise HttpError(403, "Not allowed to read bins")

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


@router.get(
    "/sync_bin",
    auth=optional_auth(),
    url_name="sync_bin",
    summary="Sync a single bin",
    description=(
        "Ingests a single bin into the database by PID. Idempotent: returns "
        "`exists` if the bin is already ingested, `synced` after a successful "
        "ingest. Requires the `bins:sync` scope (API keys, capped by the "
        "owner's permissions) or an admin session; anonymous callers are "
        "accepted for legacy compatibility with the old endpoint."
    ),
)
def sync_bin(request, dataset: str, bin: str):
    if not can_sync_bin(request.auth):
        raise HttpError(403, "Not allowed to sync bins")

    # 404s if the dataset doesn't exist
    ds = get_object_or_404(Dataset, name=dataset)

    if Bin.objects.filter(pid=bin).exists():
        return {"result": "exists"}

    synced = Accession(ds).sync_one(bin)
    if synced is None:
        raise Http404("Bin not found")

    return {"result": "synced"}
