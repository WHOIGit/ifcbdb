from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Dataset, DataDirectory, DATA_DIRECTORY_RAW

class Command(BaseCommand):
    help = 'add data directory'

    def add_arguments(self, parser):
        parser.add_argument('path', type=str, help='absolute path of directory')
        parser.add_argument('dataset', type=str, help='name of dataset to add it to')

    def handle(self, *args, **options):
        # handle arguments
        path = options['path']
        dataset_name = options['dataset']
        try:
            d = Dataset.objects.get(name=dataset_name)
        except Dataset.DoesNotExist:
            self.stderr.write('No such dataset "{}"'.format(dataset_name))
            return
        dd = DataDirectory(path=path, kind=DATA_DIRECTORY_RAW)
        dd.dataset = d
        dd.save()

