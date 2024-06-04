from typing import List

from django.http import HttpRequest
from ninja import Router
from core.models import Dataset
from .schemas import DatasetSchema


router = Router()


@router.get('/', response=List[DatasetSchema])
def list(request: HttpRequest, include_inactive: bool = False):
    datasets = Dataset.objects.all()

    if not include_inactive:
        datasets = datasets.exclude(is_active=False)

    return datasets
