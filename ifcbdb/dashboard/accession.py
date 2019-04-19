import os
import json

from django.db import IntegrityError

from .models import Bin, DataDirectory, DATA_DIRECTORY_RAW
from .qaqc import check_bad, check_no_rois

import ifcb

def sync_dataset(dataset):
    for dd in dataset.directories.filter(kind=DATA_DIRECTORY_RAW).order_by('priority'):
        if not os.path.exists(dd.path):
            continue # skip and continue searching
        directory = ifcb.DataDirectory(dd.path)
        for b in directory:
            add_bin(dataset, b)

def add_bin(dataset, bin):
    pid = bin.lid
    # before we do expensive parsing, make sure we really need to add this
    try:
        Bin.objects.get(pid=pid)
        print('skipping {}, already added'.format(pid))
        return
    except Bin.DoesNotExist:
        pass
    timestamp = bin.timestamp
    b = Bin(pid=pid, timestamp=timestamp, sample_time=timestamp)
    # qaqc checks
    qc_bad = qc_bad = check_bad(bin)
    if qc_bad:
        b.qc_bad = True
        b.save()
        # should it also be added to the dataset?
        print('bad bin {}'.format(pid))
        return
    b.qc_no_rois = check_no_rois(bin)
    # metadata
    b.metadata = json.dumps(bin.hdr_attributes)
    # metrics
    b.temperature = bin.temperature
    b.humidity = bin.humidity
    b.size = bin.fileset.getsize() # assumes FilesetBin
    b.ml_analyzed = bin.ml_analyzed
    b.look_time = bin.look_time
    b.run_time = bin.run_time
    b.save()
    dataset.bins.add(b)
    print('added {} to {}'.format(pid, dataset.name)) # FIXME use logging
