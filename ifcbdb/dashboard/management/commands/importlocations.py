from django.core.management.base import BaseCommand, CommandError

import os

import pandas as pd

from dashboard.models import Bin

BIN_ID_COLUMNS = ['id','pid','lid','bin','bin_id','sample','sample_id']
LAT_COLUMNS = ['latitude','lat','y']
LON_COLUMNS = ['longitude','lon','lng','lg','x']
DEPTH_COLUMNS = ['depth','dep','z']

class Command(BaseCommand):
    help = 'import location data'

    def add_arguments(self, parser):
        parser.add_argument('file', type=str, help='path to CSV file containing location data')

    def handle(self, *args, **options):
        # handle arguments
        path = options['file']

        assert os.path.exists(path)
        df = pd.read_csv(path)
        df.columns = [s.lower() for s in df.columns]

        for pc in BIN_ID_COLUMNS:
            if pc in df.columns:
                pid_col = pc

        for lc in LAT_COLUMNS:
            if lc in df.columns:
                lat_col = lc

        for lc in LON_COLUMNS:
            if lc in df.columns:
                lon_col = lc

        depth_column = None
        for dc in DEPTH_COLUMNS:
            if dc in df.columns:
                depth_column = dc

        for row in df.itertuples():
            pid = getattr(row, pid_col)
            lat = getattr(row, lat_col)
            lon = getattr(row, lon_col)

            try:
                b = Bin.objects.get(pid=pid)

                if depth_column is not None:
                    depth = getattr(row, depth_column)
                    b.depth = depth

                b.set_location(lon, lat)
                b.save()

                msg = '{} lat={} lon={}'.format(pid, lat, lon)
                if depth_column is not None:
                    msg = '{} depth={}'.format(msg, depth)

                print(msg)
            except Bin.DoesNotExist:
                pass
