import os
import json

from django.db import IntegrityError

from .models import Bin, DataDirectory, DATA_DIRECTORY_RAW
from .qaqc import check_bad, check_no_rois

import ifcb

def sync_dataset(dataset, lat=None, lon=None, depth=None):
    for dd in dataset.directories.filter(kind=DATA_DIRECTORY_RAW).order_by('priority'):
        if not os.path.exists(dd.path):
            continue # skip and continue searching
        directory = ifcb.DataDirectory(dd.path)
        for b in directory:
            add_bin(dataset, b, lat, lon, depth)

def add_bin(dataset, bin, lat, lon, depth):
    pid = bin.lid
    b = Bin.objects.filter(pid=pid).first()
    if b is not None:
        dataset.bins.add(b)
        print('{} was added to or remains in {}'.format(pid, dataset.name))
        return
    timestamp = bin.timestamp
    b = Bin(pid=pid, timestamp=timestamp, sample_time=timestamp)
    # qaqc checks
    qc_bad = qc_bad = check_bad(bin)
    if qc_bad:
        b.qc_bad = True
        print('{} raw data is bad'.format(pid))
        return
    # spatial information
    if lat is not None and lon is not None:
        b.set_location(lon, lat)
    if depth is not None:
        b.depth = depth
    b.qc_no_rois = check_no_rois(bin)
    # metadata
    b.metadata_json = json.dumps(bin.hdr_attributes)
    # metrics
    b.temperature = bin.temperature
    b.humidity = bin.humidity
    b.size = bin.fileset.getsize() # assumes FilesetBin
    b.ml_analyzed = bin.ml_analyzed
    b.look_time = bin.look_time
    b.run_time = bin.run_time
    b.n_triggers = len(bin)
    b.n_images = len(bin.images)
    b.concentration = b.n_images / b.ml_analyzed
    b.save()
    dataset.bins.add(b)
    print('{} created and added to {}'.format(pid, dataset.name)) # FIXME use logging
