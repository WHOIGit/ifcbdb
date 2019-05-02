from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Bin, Dataset

class Command(BaseCommand):
    """for testing only!!"""
    
    help = 'delete all bins'

    def add_arguments(self, parser):
        parser.add_argument('-ds', '--dataset', type=str, help='name of dataset')

    def handle(self, *args, **options):
        ds_name = options.get('dataset')
        if ds_name is not None:
            ds = Dataset.objects.get(name=ds_name)
            ds.bins.all().delete()
        else:
            Bin.objects.all().delete()
