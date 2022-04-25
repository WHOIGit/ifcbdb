import time

from celery import shared_task
from celery import signals

import numpy as np
import pandas as pd

from django.core.cache import cache

from .mosaic import Mosaic

@signals.worker_process_init.connect
def precompile_bin_packer(sender, **kw):
    print('precompiling bin packer', end='')
    from .mosaic import pack
    hs = np.array([10, 20, 30], dtype=np.int32)
    ws = np.array([30, 20, 10], dtype=np.int32)
    ids = np.array([0, 1, 2], dtype=np.int32)
    xs = np.zeros(3, dtype=np.int32)
    ys = np.zeros(3, dtype=np.int32)
    pages = np.zeros(3, dtype=np.int32)
    pack(100, 100, hs, ws, ys, xs, pages)

@shared_task
def mosaic_coordinates_task(bin_id, shape=(600,800), scale=0.33, cache_key=None):
    from dashboard.models import Bin
    h, w = shape
    bin = Bin.objects.get(pid=bin_id)
    b = bin._get_bin()
    m = Mosaic(b, shape=shape, scale=scale)
    then = time.time()
    coordinates = m.pack(max_pages=20)
    elapsed = time.time() - then
    print('computing mosaic coordinates for {} took {}s'.format(bin.pid, elapsed), end='')
    result = coordinates.to_dict('list')
    if cache_key is not None:
        cache.set(cache_key, result)
    return result

@shared_task(bind=True)
def sync_dataset(self, dataset_id, lock_key, cancel_key, newest_only=True):
    from dashboard.models import Dataset
    from dashboard.accession import Accession
    ds = Dataset.objects.get(id=dataset_id)
    print('syncing dataset {}'.format(ds.name))
    acc = Accession(ds, newest_only=newest_only)
    def progress_callback(p):
        self.update_state(state='PROGRESS', meta=p)
        cancel = cache.get(cancel_key)
        if cancel is not None:
            return False
        return True
    result = None
    try:
        result = acc.sync(progress_callback=progress_callback)
    finally:
        cache.delete(cancel_key) # warning: slow
        cache.delete(lock_key) # warning: slow
    return result

@shared_task(bind=True)
def import_metadata(self, json_dataframe, lock_key, cancel_key):
    from dashboard.accession import import_metadata
    df = pd.read_json(json_dataframe)
    def progress_callback(p):
        self.update_state(state='PROGRESS', meta=p)
        cancel = cache.get(cancel_key)
        if cancel is not None:
            return False
        return True
    result = None
    try:
        result = import_metadata(df, progress_callback=progress_callback)
    except:
        self.update_state(state='ERROR', meta={})
    finally:
        cache.delete(cancel_key)
        cache.delete(lock_key)
    return result
