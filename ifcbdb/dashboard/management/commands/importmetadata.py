from django.core.management.base import BaseCommand, CommandError

import os

import pandas as pd
import numpy as np

from dashboard.models import Bin

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

class Command(BaseCommand):
    help = 'import bin metadata'

    def add_arguments(self, parser):
        parser.add_argument('file', type=str, help='path to CSV file containing metadata')

    def handle(self, *args, **options):
        # handle arguments
        path = options['file']

        assert os.path.exists(path)
        df = pd.read_csv(path)
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

                b.save()
                print(b.pid)

            except Bin.DoesNotExist:
                pass
