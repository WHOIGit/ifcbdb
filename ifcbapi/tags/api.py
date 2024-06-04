from typing import List

from django.http import HttpRequest
from ninja import Router
from core.models import Tag
from .schemas import TagSchema


router = Router()


@router.get('/', response=List[TagSchema])
def list(request: HttpRequest):
    tags = Tag.objects.all()

    return tags
