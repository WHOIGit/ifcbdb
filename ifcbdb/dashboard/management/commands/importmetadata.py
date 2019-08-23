from django.core.management.base import BaseCommand, CommandError

import os

import pandas as pd
import numpy as np

from dashboard.models import Bin

from dashboard.accession import import_metadata

class Command(BaseCommand):
    help = 'import bin metadata'

    def add_arguments(self, parser):
        parser.add_argument('file', type=str, help='path to CSV file containing metadata')

    def handle(self, *args, **options):
        # handle arguments
        path = options['file']

        assert os.path.exists(path)
        df = pd.read_csv(path)

        import_metadata(df, progress_callback=print)