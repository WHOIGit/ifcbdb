from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Dataset, FILL_VALUE
from dashboard.accession import Accession

from ifcb import DataDirectory

class Command(BaseCommand):
    help = 'sync data directories to db'

    def add_arguments(self, parser):
        parser.add_argument('dataset', type=str, help='name of dataset to add bins to')
        parser.add_argument('-lat','--latitude', type=float, help='latitiude to set all bins to')
        parser.add_argument('-lon','--longitude', type=float, help='longitude to set all bins to')
        parser.add_argument('-d', '--depth', type=float, help='depth to set all bins to')

    def handle(self, *args, **options):
        # handle arguments
        dataset_name = options['dataset']
        lat = options.get('latitude')
        lon = options.get('longitude')
        depth = options.get('depth')
        if (lat is None and lon is not None) or (lat is not None and lon is None):
            raise ValueError('must set both lat and lon')
        try:
            d = Dataset.objects.get(name=dataset_name)
        except Dataset.DoesNotExist:
            self.stderr.write('No such dataset "{}"'.format(dataset_name))
            return
        acc = Accession(d, lat=lat, lon=lon, depth=depth)
        acc.sync(progress_callback=print, log_callback=print)
