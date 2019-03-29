from django.db import IntegrityError

from .models import Bin, DataDirectory, DATA_DIRECTORY_RAW

import ifcb

def bin_verify(bin):
    return {}

def bin_metadata(bin):
    return {}

def as_ifcb_data_directory(dd):
    # FIXME handle white/blacklist
    path = dd.path
    return ifcb.DataDirectory(path)

def sync_dataset(dataset):
    for dd in dataset.directories.all(): # FIXME order by priority
        directory = as_ifcb_data_directory(dd)
        for b in directory:
            add_bin(dataset, b)

def add_bin(dataset, bin):
    pid = bin.lid
    try:
        metrics = bin_verify(bin)
        metadata = bin_metadata(bin)
        timestamp = bin.timestamp
        b = Bin(pid=pid, timestamp=timestamp, sample_time=timestamp)
        b.save()
        dataset.bins.add(b)
        print('added {} to {}'.format(pid, dataset.name)) # FIXME use logging
    except IntegrityError:
        # bin already exists, skip
        print('skipping {}, already added'.format(bin))

