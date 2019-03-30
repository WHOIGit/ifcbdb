from django.db import IntegrityError

from .models import Bin, DataDirectory, DATA_DIRECTORY_RAW

import ifcb

def as_ifcb_data_directory(dd):
    # FIXME handle white/blacklist
    path = dd.path
    return ifcb.DataDirectory(path)

def sync_dataset(dataset):
    for dd in dataset.directories.filter(kind=DATA_DIRECTORY_RAW): # FIXME order by priority
        directory = as_ifcb_data_directory(dd)
        for b in directory:
            add_bin(dataset, b)

def add_bin(dataset, bin):
    pid = bin.lid
    try:
        timestamp = bin.timestamp
        b = Bin(pid=pid, timestamp=timestamp, sample_time=timestamp)
        b.temperature = bin.temperature
        b.humidity = bin.humidity
        b.size = bin.fileset.getsize()
        b.ml_analyzed = bin.ml_analyzed
        b.look_time = bin.look_time
        b.run_time = bin.run_time
        b.save()
        dataset.bins.add(b)
        print('added {} to {}'.format(pid, dataset.name)) # FIXME use logging
    except IntegrityError:
        # bin already exists, skip
        print('skipping {}, already added'.format(bin))

