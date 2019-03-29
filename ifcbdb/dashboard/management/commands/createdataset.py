from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Dataset

class Command(BaseCommand):
    help = 'create dataset'

    def add_arguments(self, parser):
        parser.add_argument('name', type=str, help='short label for dataset (no spaces)')
        parser.add_argument('-t','--title', type=str, help='title of dataset')

    def handle(self, *args, **options):
        # handle arguments
        name = options['name']
        if options['title']:
            title = options['title']
        else:
            title = name
        # create the dataset
        d = Dataset(name=name, title=title)
        d.save()
