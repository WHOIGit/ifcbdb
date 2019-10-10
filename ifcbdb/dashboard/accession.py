import os
import json
import time

from itertools import islice

from django.db import IntegrityError, transaction

import pandas as pd
import numpy as np

from .models import Bin, DataDirectory, Instrument, Timeline
from .qaqc import check_bad, check_no_rois

import ifcb
from ifcb.data.files import time_filter
from ifcb.data.adc import SCHEMA_VERSION_1
from ifcb.data.stitching import InfilledImages

def progress(bin_id, added, total, bad):
    return {
        'bin_id': bin_id,
        'added': added,
        'total': total,
        'bad': bad,
        'existing': total - added - bad,
    }

def do_nothing(*args, **kwargs):
    pass

class Accession(object):
    # wraps a dataset object to provide accession
    def __init__(self, dataset, batch_size=100, lat=None, lon=None, depth=None, newest_only=False):
        self.dataset = dataset
        self.batch_size = batch_size
        self.lat = lat
        self.lon = lon
        self.depth = depth
        self.newest_only = newest_only
    def start_time(self):
        if not self.newest_only or not self.dataset.bins:
            return None
        b = Timeline(self.dataset.bins).most_recent_bin()
        if b:
            return b.sample_time
        return None
    def scan(self):
        for dd in self.dataset.directories.filter(kind=DataDirectory.RAW).order_by('priority'):
            if not os.path.exists(dd.path):
                continue # skip and continue searching
            directory = ifcb.DataDirectory(dd.path)
            for b in directory:
                yield b
    def sync(self, progress_callback=do_nothing, log_callback=do_nothing):
        progress_callback(progress('',0,0,0))
        bins_added = 0
        total_bins = 0
        bad_bins = 0
        most_recent_bin_id = ''
        newest_done = False
        scanner = self.scan()
        start_time = self.start_time()
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
                log_callback('{} found'.format(pid))
                instrument = instruments[bin.pid.instrument]
                timestamp = bin.timestamp
                if start_time is not None and bin.timestamp <= start_time:
                    continue
                b, created = Bin.objects.get_or_create(pid=pid, defaults={
                    'timestamp': timestamp,
                    'sample_time': timestamp,
                    'instrument': instrument,
                    'skip': True, # in case accession is interrupted
                })
                if not created:
                    self.dataset.bins.add(b)
                    continue
                b2s = self.add_bin(bin, b)
                if b2s is not None:
                    bins2save.append(b2s)
                elif created: # created, but bad! delete
                    log_callback('{} deleting bad bin'.format(b.pid))
                    b.delete()
                    bad_bins += 1
                else:
                    log_callback('{} not adding bin'.format(b.pid))
            with transaction.atomic():
                for b in bins2save:
                    b.skip = False # unskip because we're ready to save
                    b.save()
                    log_callback('{} saved'.format(b.pid))
                # add to dataset, unless the bin has no rois
                for b in bins2save:
                    if b.qc_no_rois:
                        continue
                    self.dataset.bins.add(b)
                    bins_added += 1
            # done with the batch
            status = progress_callback(progress(most_recent_bin_id, bins_added, total_bins, bad_bins))
            if not status: # cancel
                break
        # done.
        prog = progress(most_recent_bin_id, bins_added, total_bins, bad_bins)
        progress_callback(prog)
        return prog
    def add_bin(self, bin, b): # IFCB bin, Bin instance
        # qaqc checks
        qc_bad = check_bad(bin)
        if qc_bad:
            b.qc_bad = True
            return
        # more error checking for setting attributes
        try:
            ml_analyzed = bin.ml_analyzed
            if ml_analyzed <= 0:
                qc_bad = True
        except:
            qc_bad = True
        # metadata
        try:
            b.metadata_json = json.dumps(bin.hdr_attributes)
        except:
            qc_bad = True
        #
        if qc_bad:
            b.qc_bad = True
            return
        # spatial information
        if self.lat is not None and self.lon is not None:
            b.set_location(self.lon, self.lat)
        if self.depth is not None:
            b.depth = self.depth
        b.qc_no_rois = check_no_rois(bin)
        # metrics
        try:
            b.temperature = bin.temperature
        except KeyError: # older data
            b.temperature = 0
        try:
            b.humidity = bin.humidity
        except KeyError: # older data
            b.humidity = 0
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

def import_progress(bin_id, n_modded):
    return {
        'bin': bin_id,
        'n_modded': n_modded,
    }

def import_metadata(metadata_dataframe, progress_callback=do_nothing):
    df = metadata_dataframe.copy()

    BIN_ID_COLUMNS = ['id','pid','lid','bin','bin_id','sample','sample_id']
    LAT_COLUMNS = ['latitude','lat','y']
    LON_COLUMNS = ['longitude','lon','lng','lg','x']
    DEPTH_COLUMNS = ['depth','dep','z']
    TIMESTAMP_COLUMNS = ['date', 'timestamp', 'datetime']
    MA_COLUMNS = ['ml_analyzed']
    COMMENTS_COLUMNS = ['comment','comments','note','notes']
    TAG_COLUMN_PREFIX = 'tag'
    SKIP_COLUMNS = ['skip','bad']

    SKIP_POSITIVE_VALUES = ['skip','yes','y','true','t']
    SKIP_NEGATIVE_VALUES = ['noskip','no','n','false','f']

    def get_column(df, possible_names):
        for possible in possible_names:
            if possible in df.columns:
                return possible
        return None

    def get_cell(named_tup, key):
        val = getattr(named_tup, key)
        try:
            if np.isnan(val):
                return None
            else:
                return val
        except TypeError:
            return val

    df.columns = [s.lower() for s in df.columns]

    pid_col = get_column(df, BIN_ID_COLUMNS)

    if pid_col is None:
        raise KeyError('need to specify bin ID column')

    lat_col = get_column(df, LAT_COLUMNS)
    lon_col = get_column(df, LON_COLUMNS)

    if (lat_col is None and lon_col is not None) or (lat_col is not None and lon_col is None):
        raise KeyError('location metadata must include both latitude and longitude')

    depth_col = get_column(df, DEPTH_COLUMNS)

    ts_col = get_column(df, TIMESTAMP_COLUMNS)

    skip_col = get_column(df, SKIP_COLUMNS)

    comments_col = get_column(df, COMMENTS_COLUMNS)

    ma_col = get_column(df, MA_COLUMNS)

    tag_cols = []
    for c in df.columns:
        if c.startswith('tag'):
            tag_cols.append(c)

    n_modded = 0
    progress_batch_size = 100

    for row in df.itertuples():
        pid = get_cell(row, pid_col)
        if pid is None:
            raise ValueError('bin id must be specified')

        try:
            b = Bin.objects.get(pid=pid)

            if b is None:
                raise KeyError('no such bin {}'.format(pid))

            # spatiotemporal metadata

            if ts_col is not None:
                ts_str = get_cell(row, ts_col)
                ts = pd.to_datetime(ts_str, utc=True)
                if ts is not None:
                    b.sample_time = ts
           
            if lat_col is not None and lon_col is not None:
                lat = get_cell(row, lat_col)
                lon = get_cell(row, lon_col)
                if lat is not None and lon is not None:
                    b.set_location(lon, lat)

            if depth_col is not None:
                depth = get_cell(row, depth_col)
                if depth is not None:
                    b.depth = depth

            # ml_analyzed

            if ma_col is not None:
                ml_analyzed = get_cell(row, ma_col)
                if ml_analyzed is not None:
                    b.set_ml_analyzed(ml_analyzed)

            # tags and comments

            if tag_cols:
                for c in tag_cols:
                    tag = get_cell(row, c)
                    if tag is not None:
                        b.add_tag(tag)

            if comments_col is not None:
                body = get_cell(row, comments_col)
                if body is not None:
                    b.add_comment(body)

            # skip flag

            if skip_col is not None:
                skip = get_cell(row, skip_col)
                if skip is None:
                    pass
                elif skip in SKIP_POSITIVE_VALUES:
                    b.skip = True
                elif skip in SKIP_NEGATIVE_VALUES:
                    b.skip = False

            n_modded += 1
            b.save()
            
            if n_modded % progress_batch_size == 0:
                progress_callback(import_progress(b.pid, n_modded))

        except ValueError:
            pass

        except KeyError:
            pass

        except Bin.DoesNotExist:
            pass

    progress_callback(import_progress(b.pid, n_modded))
