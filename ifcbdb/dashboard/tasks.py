from celery import shared_task
from django.core.cache import cache
from dashboard.models import Bin

@shared_task
def test_celery():
    b = Bin.objects.order_by('?').first()
    cache.set('random_bin',b,timeout=None)
    print(b)
    return b.pid
