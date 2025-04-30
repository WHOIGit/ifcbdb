from pprint import pprint
import os
import json
import time
import re

from collections import defaultdict
from itertools import islice

from django.db import IntegrityError, transaction
from django.db.models import Count, Max
from django.contrib.postgres.aggregates.general import StringAgg

import pandas as pd
import numpy as np

from .models import Bin, DataDirectory, Instrument, Timeline, Dataset, normalize_tag_name
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
def print_progress(progress):
        print(progress)
        return True

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

            directory = ifcb.DataDirectory(dd.path, require_roi_files=dd.require_roi_files)
            for b in directory:
                # Bins do not have a require_roi_files property, but we're adding it here anyway to pass
                #   along the associated directory's setting through to the next call
                b.require_roi_files = dd.require_roi_files
                yield b
    def sync_one(self, pid):
        bin = None
        directory = None
        for dd in self.dataset.directories.filter(kind=DataDirectory.RAW).order_by('priority'):
            if not os.path.exists(dd.path):
                continue # skip and continue searching
            directory = ifcb.DataDirectory(dd.path, require_roi_files=dd.require_roi_files)
            try:
                bin = directory[pid]
            except KeyError:
                continue
        if bin is None:
            return 'bin {} not found'.format(pid)

        # create instrument if necessary
        i = bin.pid.instrument
        version = bin.pid.schema_version
        instrument, created = Instrument.objects.get_or_create(number=i, defaults={
            'version': version
        })
        # create model object
        timestamp = bin.pid.timestamp
        b, created = Bin.objects.get_or_create(pid=pid, defaults={
            'timestamp': timestamp,
            'sample_time': timestamp,
            'instrument': instrument,
            'skip': True, # in case accession is interrupted
        })
        if not created and not dataset in b.datasets:
            self.dataset.bins.add(b)
            return 
        b2s, error = self.add_bin(bin, b)
        if error is not None:
            # there was an error. if we created a bin, delete it
            if created:
                b.delete()
                return error
        with transaction.atomic():
            if not b2s.qc_no_rois:
                b2s.skip = False
                b2s.save()
                self.dataset.bins.add(b2s)
            else:
                b2s.save()
    def sync(self, progress_callback=do_nothing, log_callback=do_nothing):
        progress_callback(print_progress(progress('',0,0,0,{})))
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

    def add_bin(self, bin, b, require_roi_files=True): # IFCB bin, Bin instance
        # qaqc checks
        qc_bad = check_bad(bin)
        if qc_bad:
            b.qc_bad = True
            return b, 'malformed raw data'
        no_rois = require_roi_files and check_no_rois(bin)
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
            headers = bin.hdr_attributes
        except Exception as e:
            b.qc_bad = True
            return b, 'header: {}'.format(str(e))
        b.metadata_json = json.dumps(headers)
        #
        # lat/lon/depth
        latitude = headers.get('latitude') or headers.get('gpsLatitude')
        longitude = headers.get('longitude') or headers.get('gpsLongitude')

        depth = headers.get('depth')
        if latitude is not None and longitude is not None:
            try:
                latitude = float(latitude)
                longitude = float(longitude)
            except (TypeError, ValueError):
                latitude = None
                longitude = None
            try:
                depth = float(depth)
            except TypeError:
                depth = None
            if latitude is not None and longitude is not None:
                b.set_location(longitude, latitude, depth)
        #
        b.qc_no_rois = require_roi_files and check_no_rois(bin)
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
        b.n_triggers = bin.n_triggers
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
    LAT_COLUMNS = ['latitude','lat','y','gpsLatitude']
    LON_COLUMNS = ['longitude','lon','lng','lg','x','gpsLongitude']
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

    SKIP_POSITIVE_VALUES = ['skip','yes','y','true','t','1']
    SKIP_NEGATIVE_VALUES = ['noskip','no','n','false','f','0']

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
                    cell = get_cell(row, c)
                    if cell is None:
                        continue

                    tag = str(get_cell(row, c)).strip()
                    if tag == '':
                        continue

                    normalized = normalize_tag_name(tag)
                    if not tag or not normalized:
                        raise ValueError('blank tag name "{}"'.format(tag))
                    if re.match(r'^[0-9]+$',normalized):
                        raise ValueError('tag "{}" consists of digits'.format(tag))
                    b.add_tag(normalized)

            if comments_col is not None:
                body = get_cell(row, comments_col)
                if body is not None:
                    b.add_comment(body, skip_duplicates=True)

            # skip flag

            if skip_col is not None:
                skip = get_cell(row, skip_col)
                if skip is None:
                    pass
                elif type(skip) is bool:
                    b.skip = skip
                elif type(skip) is int and skip in [0,1]:
                    b.skip = bool(skip)
                elif type(skip) is str:
                    if skip.lower() in SKIP_POSITIVE_VALUES:
                        b.skip = True
                    elif skip.lower() in SKIP_NEGATIVE_VALUES:
                        b.skip = False
                else:
                    raise ValueError(
                        'skip value "{}" had unsupported type "{}"'.format(skip, type(skip).__name__))

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

def export_metadata(ds, bins):
    # Maximum number of bins this export can return. The limit is relatively arbitrary, and in place to prevent runaway
    #   queries returning lots of data when no search parameters are defined
    max_results = 500_000

    name = ds.name if ds else ''
    dataset_location = ds.location if ds else None
    dataset_depth = ds.depth if ds else None
    bqs = bins

    qs = bqs.values('id','pid','sample_time','location','ml_analyzed',
        'cruise','cast','niskin','depth', 'instrument__number', 'skip',
        'sample_type', 'n_images', 'tags__name').order_by('pid','tags__name')

    # fetch all tags and compute number of tag columns
    tags_by_id = defaultdict(list)
    n_tag_cols = 0
    for item in qs:
        tag_name = item['tags__name']
        if tag_name:
            id = item['id']
            tags = tags_by_id[id]
            tags.append(tag_name)
            if len(tags) > n_tag_cols:
                n_tag_cols = len(tags)
    # fetch all comment summaries
    comment_summary_by_id = \
        dict(bqs.filter(comments__isnull=False).values_list('id') \
             .annotate(comment_summary=StringAgg('comments__content', delimiter='; ', ordering='comments__timestamp')))
    # fetch selected metadata fields
    # PMTtriggerSelection_DAQ_MCConly
    trigger_selection_key = 'PMTtriggerSelection_DAQ_MCConly'
    id2md = bqs.filter(metadata_json__contains=trigger_selection_key).values_list('id', 'metadata_json')
    trigger_selection_by_id = dict([(id, json.loads(md).get(trigger_selection_key)) for id, md in id2md])
    # now construct the dataframe
    r = defaultdict(list)

    # Only add the name column if dataset criteria was provided
    if name:
        r.update({'dataset': name})

    # fast way to remove duplicates
    prev_pid = None

    # The "all()" is required to make sure there's a LIMIT statement added the query, rather than pulling back all
    #   records and then taking part of the list
    qs = qs.all()[:max_results]

    for item in qs:
        if item['pid'] == prev_pid:
            continue
        prev_pid = item['pid']

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
        add('sample_type')
        add('n_images')
        tag_names = tags_by_id[item['id']]
        for i in range(n_tag_cols):
            v = tag_names[i] if i < len(tag_names) else ''
            r[f'tag{i+1}'].append(v)
        r['comment_summary'].append(comment_summary_by_id.get(item['id'], ''))
        r['trigger_selection'].append(trigger_selection_by_id.get(item['id'], ''))
        r['skip'].append(1 if item['skip'] else 0)

    df = pd.DataFrame(r)

    return df