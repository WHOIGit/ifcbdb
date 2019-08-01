import os
import json
import time

from itertools import islice

from django.db import IntegrityError, transaction

from .models import Bin, DataDirectory, Instrument
from .qaqc import check_bad, check_no_rois

import ifcb
from ifcb.data.adc import SCHEMA_VERSION_1
from ifcb.data.stitching import InfilledImages

def progress(bin_id, added, total):
    return {
        'bin_id': bin_id,
        'added': added,
        'total': total,
        'existing': total - added,
    }

def do_nothing(*args, **kwargs):
    pass

class Accession(object):
    # wraps a dataset object to provide accession
    def __init__(self, dataset, lat=None, lon=None, depth=None):
        self.dataset = dataset
        self.batch_size = 100
        self.lat = lat
        self.lon = lon
        self.depth = depth
    def scan(self):
        for dd in self.dataset.directories.filter(kind=DataDirectory.RAW).order_by('priority'):
            if not os.path.exists(dd.path):
                continue # skip and continue searching
            directory = ifcb.DataDirectory(dd.path)
            for b in directory:
                yield b
    def sync(self, progress_callback=do_nothing):
        progress_callback(progress('',0,0))
        bins_added = 0
        total_bins = 0
        most_recent_bin_id = ''
        scanner = self.scan()
        while True:
            bins = list(islice(scanner, self.batch_size))
            if not bins:
                break
            total_bins += len(bins)
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
            then = time.time()
            bins2save = []
            for bin in bins:
                pid = bin.lid
                most_recent_bin_id = pid
                instrument = instruments[bin.pid.instrument]
                timestamp = bin.timestamp
                b, created = Bin.objects.get_or_create(pid=pid, defaults={
                    'timestamp': timestamp,
                    'sample_time': timestamp, # FIXME read from schema 2 header files
                    'instrument': instrument,
                })
                if not created:
                    self.dataset.bins.add(b)
                    continue
                b2s = self.add_bin(bin, b)
                if b2s is not None:
                    bins2save.append(b2s)
                elif created: # created, but bad! delete
                    b.delete()
            with transaction.atomic():
                for b in bins2save:
                    b.save()
                # add to dataset, unless the bin has no rois
                for b in bins2save and not b.qc_no_rois:
                    self.dataset.bins.add(b)
                    bins_added += 1
                    most_recent_bin_id = b.pid
            progress_callback(progress(most_recent_bin_id, bins_added, total_bins))
        # done.
        prog = progress(most_recent_bin_id, bins_added, total_bins)
        progress_callback(prog)
        return prog
    def add_bin(self, bin, b): # IFCB bin, Bin instance
        # qaqc checks
        qc_bad = check_bad(bin)
        ml_analyzed = bin.ml_analyzed
        if ml_analyzed <= 0:
            qc_bad = True
        if qc_bad:
            b.qc_bad = True
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
        b.ml_analyzed = ml_analyzed
        b.look_time = bin.look_time
        b.run_time = bin.run_time
        b.n_triggers = len(bin)
        if bin.pid.schema_version == SCHEMA_VERSION_1:
            ii = InfilledImages(bin)
            b.n_images = len(ii)
        else:
            b.n_images = len(bin.images)
        b.concentration = b.n_images / ml_analyzed
        if b.concentration < 0: # metadata is bogus!
            return
        return b # defer save
