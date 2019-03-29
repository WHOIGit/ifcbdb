from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Dataset
from dashboard.accession import sync_dataset

from ifcb import DataDirectory

class Command(BaseCommand):
    help = 'sync data directories to db'

    def add_arguments(self, parser):
        parser.add_argument('dataset', type=str, help='name of dataset to add bins to')

    def handle(self, *args, **options):
        # handle arguments
        dataset_name = options['dataset']
        try:
            d = Dataset.objects.get(name=dataset_name)
        except Dataset.DoesNotExist:
            self.stderr.write('No such dataset "{}"'.format(dataset_name))
            return
        sync_dataset(d)
