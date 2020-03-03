import os
import json
import time

from collections import defaultdict
from itertools import islice

from django.db import IntegrityError, transaction

import pandas as pd
import numpy as np

from .models import Bin, DataDirectory, Instrument, Timeline, Dataset
from .qaqc import check_bad, check_no_rois

import ifcb
from ifcb.data.files import time_filter
from ifcb.data.adc import SCHEMA_VERSION_1
from ifcb.data.stitching import InfilledImages

def progress(bin_id, added, total, bad, errors={}):
    error_list = [{ 'bin': k, 'message': v} for k,v in errors.items()]
    return {
        'bin_id': bin_id,
        'added': added,
        'total': total,
        'bad': bad,
        'existing': total - added - bad,
        'errors': error_list,
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
        progress_callback(progress('',0,0,0,{}))
        bins_added = 0
        total_bins = 0
        bad_bins = 0
        most_recent_bin_id = ''
        newest_done = False
        scanner = self.scan()
        start_time = self.start_time()
        errors = {}
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
                b2s, error = self.add_bin(bin, b)
                if error is not None:
                    b2s = None
                    errors[b.pid] = error
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
            status = progress_callback(progress(most_recent_bin_id, bins_added, total_bins, bad_bins, errors))
            if not status: # cancel
                break
        # done.
        prog = progress(most_recent_bin_id, bins_added, total_bins, bad_bins, errors)
        progress_callback(prog)
        return prog
    def add_bin(self, bin, b): # IFCB bin, Bin instance
        # qaqc checks
        qc_bad = check_bad(bin)
        if qc_bad:
            b.qc_bad = True
            return b, 'malformed raw data'
        no_rois = check_no_rois(bin)
        if no_rois:
            b.qc_bad = True
            return b, 'zero ROIs'
        # more error checking for setting attributes
        try:
            ml_analyzed = bin.ml_analyzed
            if ml_analyzed <= 0:
                b.qc_bad = True
                return b, 'ml_analyzed <= 0'
        except Exception as e:
            b.qc_bad = True
            return b, 'ml_analyzed: {}'.format(str(e))
        # metadata
        try:
            b.metadata_json = json.dumps(bin.hdr_attributes)
        except Exception as e:
            b.qc_bad = True
            return b, 'header: {}'.format(str(e))
        #
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
            return b, 'rois/ml is < 0'
        return b, None # defer save

def import_progress(bin_id, n_modded, errors, done=False):
    #print(bin_id, n_modded, errors, error_message, done) # FIXME debug
    return {
        'bin': bin_id,
        'n_modded': n_modded,
        'errors': errors,
        'done': done,
    }

def import_metadata(metadata_dataframe, progress_callback=do_nothing):
    df = metadata_dataframe.copy()

    BIN_ID_COLUMNS = ['id','pid','lid','bin','bin_id','sample','sample_id','filename']
    LAT_COLUMNS = ['latitude','lat','y']
    LON_COLUMNS = ['longitude','lon','lng','lg','x']
    DEPTH_COLUMNS = ['depth','dep','z']
    TIMESTAMP_COLUMNS = ['date', 'timestamp', 'datetime']
    MA_COLUMNS = ['ml_analyzed']
    COMMENTS_COLUMNS = ['comment','comments','note','notes']
    TAG_COLUMN_PREFIX = 'tag'
    SKIP_COLUMNS = ['skip','bad']
    CRUISE_COLUMNS = ['cruise']
    CAST_COLUMNS = ['cast']
    NISKIN_COLUMNS = ['niskin','bottle']
    SAMPLE_TYPE_COLUMNS = ['sampletype','sample_type']

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
            if pd.isnull(val):
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

    cruise_col = get_column(df, CRUISE_COLUMNS)
    cast_col = get_column(df, CAST_COLUMNS)
    niskin_col = get_column(df, NISKIN_COLUMNS)

    sample_type_col = get_column(df, SAMPLE_TYPE_COLUMNS)

    tag_cols = []
    for c in df.columns:
        if c.startswith('tag'):
            tag_cols.append(c)

    n_modded = 0
    progress_batch_size = 50

    b = None
    errors = []

    should_continue = True

    for row in df.itertuples():
        if not should_continue:
            break

        try:
            pid = get_cell(row, pid_col)
            if pid is None:
                raise ValueError('bin id must be specified')

            try:
                b = Bin.objects.get(pid=pid)
            except Bin.DoesNotExist:
                raise KeyError('Bin {} not found'.format(pid))

            # spatiotemporal metadata

            if ts_col is not None:
                ts_str = get_cell(row, ts_col)
                if ts_str is not None:
                    ts = pd.to_datetime(ts_str, utc=True)
                    if not pd.isnull(ts):
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

            # sample type

            if sample_type_col is not None:
                sample_type = get_cell(row, sample_type_col)
                if sample_type is not None:
                    b.sample_type = sample_type

            # cruise / cast / niskin

            if cruise_col is not None:
                cruise = get_cell(row, cruise_col)
                if cruise is not None:
                    b.cruise = str(cruise)

            if cast_col is not None:
                cast = get_cell(row, cast_col)
                if cast is not None:
                    try:
                        cast_number = int(cast)
                        b.cast = str(cast_number)
                    except ValueError:
                        b.cast = str(cast)

            if niskin_col is not None:
                niskin = get_cell(row, niskin_col)
                if niskin is not None:
                    b.niskin = int(niskin)

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
                    b.add_comment(body, skip_duplicates=True)

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
                should_continue = progress_callback(import_progress(b.pid, n_modded, errors))

        except Exception as e:
            errors.append({
                'row': row.Index + 2, # why 2 and not 1?
                'message': str(e),
                })

    if b is not None:
        progress = import_progress(b.pid, n_modded, errors, True)
    else:
        progress = import_progress('', n_modded, errors, True)

    progress_callback(progress)

    return progress

def export_metadata(dataset_name):
    name = dataset_name
    ds = Dataset.objects.get(name=name)
    dataset_location = ds.location
    dataset_depth = ds.depth
    qs = ds.bins.values('id','pid','sample_time','location','ml_analyzed', 'cruise','cast','niskin','depth', 'instrument__number', 'skip').order_by('pid')
    r = defaultdict(list)
    r.update({ 'dataset': name })
    for item in qs:
        def add(field, rename=None):
            if rename is not None:
                r[rename].append(item[field])
            else:
                r[field].append(item[field])
        add('pid')
        add('sample_time')
        add('instrument__number', rename='ifcb')
        add('ml_analyzed')
        if item['location'] is not None:
            r['latitude'].append(item['location'].y)
            r['longitude'].append(item['location'].x)
        elif dataset_location is not None:
            r['latitude'].append(dataset_location.y)
            r['longitude'].append(dataset_location.x)
        else:
            r['latitude'].append(np.nan)
            r['longitude'].append(np.nan)
        if item['depth'] is not None:
            add('depth')
        elif dataset_depth is not None:
            r['depth'].append(dataset_depth)
        else:
            r['depth'].append(np.nan)
        add('cruise')
        add('cast')
        add('niskin')
        r['skip'].append(1 if item['skip'] else 0)

    df = pd.DataFrame(r)

    return df