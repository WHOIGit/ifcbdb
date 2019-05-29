import os
import json
import time

from itertools import islice

from django.db import IntegrityError, transaction

from .models import Bin, DataDirectory, DATA_DIRECTORY_RAW, Instrument
from .qaqc import check_bad, check_no_rois

import ifcb
from ifcb.data.stitching import InfilledImages

class Accession(object):
    # wraps a dataset object to provide accession
    def __init__(self, dataset, lat=None, lon=None, depth=None):
        self.dataset = dataset
        self.batch_size = 100
        self.lat = lat
        self.lon = lon
        self.depth = depth
    def scan(self):
        for dd in self.dataset.directories.filter(kind=DATA_DIRECTORY_RAW).order_by('priority'):
            if not os.path.exists(dd.path):
                continue # skip and continue searching
            directory = ifcb.DataDirectory(dd.path)
            for b in directory:
                yield b
    def sync(self):
        print('scanning {}...'.format(self.dataset.name))
        scanner = self.scan()
        while True:
            bins = list(islice(scanner, self.batch_size))
            if not bins:
                break
            # create instrument(s)
            instruments = {} # keyed by instrument number
            for bin in bins:
                i = bin.pid.instrument
                if not i in instruments:
                    version = bin.pid.schema_version
                    instrument, created = Instrument.objects.get_or_create(number=i, defaults={
                        'version': version
                    })
                    instruments[i] = instrument
            # create bins
            print('processing {} bin(s)'.format(len(bins)))
            then = time.time()
            bins2save = []
            for bin in bins:
                pid = bin.lid
                instrument = instruments[bin.pid.instrument]
                timestamp = bin.timestamp
                b, created = Bin.objects.get_or_create(pid=pid, defaults={
                    'timestamp': timestamp,
                    'sample_time': timestamp, # FIXME read from schema 2 header files
                    'instrument': instrument,
                })
                if not created:
                    self.dataset.bins.add(b)
                    print('{} was added to or remains in {}'.format(pid, self.dataset.name))
                    continue
                bins2save.append(self.add_bin(bin, b))
            with transaction.atomic():
                for b in bins2save:
                    b.save()
                    print('{} created'.format(b.pid))
                for b in bins2save:
                    self.dataset.bins.add(b)
                    print('{} added to {}'.format(b.pid, self.dataset.name))
            elapsed = time.time() - then
            print('processed {} bin(s) in {:.3f}s'.format(len(bins), elapsed))
    def add_bin(self, bin, b): # IFCB bin, Bin instance
        print('{} checking and processing'.format(b.pid))
        # qaqc checks
        qc_bad = qc_bad = check_bad(bin)
        if qc_bad:
            b.qc_bad = True
            print('{} raw data is bad'.format(pid))
            return
        # spatial information
        if self.lat is not None and self.lon is not None:
            b.set_location(self.lon, self.lat)
        if self.depth is not None:
            b.depth = self.depth
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
        if bin.pid.schema_version == 1:
            ii = InfilledImages(bin)
            b.n_images = len(ii)
        else:
            b.n_images = len(bin.images)
        b.concentration = b.n_images / b.ml_analyzed
        return b # defer save
