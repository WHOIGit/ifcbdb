from celery import shared_task

from django.core.cache import cache

from dashboard.models import Bin

@shared_task
def mosaic_coordinates_task(bin_id, shape=(600,800), scale=0.33):
    b = Bin.objects.get(pid=bin_id)
    print('computing mosaic coordinates for {}'.format(b))
    b.mosaic_coordinates(shape, scale)
