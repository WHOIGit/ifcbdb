from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Dataset, DataDirectory, DATA_DIRECTORY_RAW, DATA_DIRECTORY_BLOBS

class Command(BaseCommand):
    help = 'add data directory'

    def add_arguments(self, parser):
        parser.add_argument('path', type=str, help='absolute path of directory')
        parser.add_argument('dataset', type=str, help='name of dataset to add it to')
        parser.add_argument('-k','--kind', type=str, help='kind of dataset (e.g., raw/blobs)')
        parser.add_argument('-p','--product_version', type=int, help='product version (e.g., 2)')

    def handle(self, *args, **options):
        # handle arguments
        path = options['path']
        dataset_name = options['dataset']
        if options['kind']:
            kind = options['kind']
            assert kind in [DATA_DIRECTORY_RAW, DATA_DIRECTORY_BLOBS]
        else:
            kind = DATA_DIRECTORY_RAW
        version = None
        if kind != DATA_DIRECTORY_RAW:
            assert options['product_version']
            version = options['product_version']
        # find the dataset
        try:
            d = Dataset.objects.get(name=dataset_name)
        except Dataset.DoesNotExist:
            self.stderr.write('No such dataset "{}"'.format(dataset_name))
            return
        # create the directory
        dd = DataDirectory(path=path, kind=kind)
        dd.dataset = d
        if version is not None:
            dd.version = version
        dd.save()

