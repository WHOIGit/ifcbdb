from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Dataset, DataDirectory

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
            assert kind in [DataDirectory.RAW, DataDirectory.BLOBS, DataDirectory.FEATURES]
        else:
            kind = DataDirectory.RAW
        version = None
        if kind != DataDirectory.RAW:
            assert options['product_version']
            version = options['product_version']
        # find the dataset
        try:
            d = Dataset.objects.get(name=dataset_name)
        except Dataset.DoesNotExist:
            self.stderr.write('No such dataset "{}"'.format(dataset_name))
            return

        # make sure the directory path is not already in the database
        existing_path = DataDirectory.objects.filter(dataset=d, path=path, kind=kind).first()
        if existing_path:
            self.stderr.write('Path "{}" (kind: {}) is already in use by dataset "{}"'.format(path, kind, existing_path.dataset.name))
            return

        # create the directory
        dd = DataDirectory(path=path, kind=kind)
        dd.dataset = d
        if version is not None:
            dd.version = version
        dd.save()

