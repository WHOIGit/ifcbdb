from celery import shared_task

from django.core.cache import cache

from dashboard.models import Bin

@shared_task
def test_celery(arg):
    print('arg = {}'.format(arg))
    b = Bin.objects.order_by('?').first()
    cache.set('random_bin',b,timeout=None)
    print(b)
    return b.pid

@shared_task
def mosaic_coordinates_task(bin_id, shape=(600,800), scale=0.33):
    b = Bin.objects.get(pid=bin_id)
    print('computing mosaic coordinates for {}'.format(b))
    b.mosaic_coordinates(shape, scale)
