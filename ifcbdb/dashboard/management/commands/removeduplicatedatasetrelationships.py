from collections import deque
from dashboard.models import Bin, bin_query, Dataset
from django.core.management.base import BaseCommand, CommandError


def get_bins_in_datasets(dataset1, dataset2):
    qs1 = Bin.objects.filter(datasets__name=dataset1)
    qs2 = qs1.filter(datasets__name=dataset2)
    print("Number of bins associated with both given datasets: " + str(qs2.count()))
    return qs2

def verify_dataset_exists(dataset_name):
    if Dataset.objects.filter(name=dataset_name).count() < 1:
        raise CommandError(print('specified {} does not exist'.format(dataset_name)))


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('-d1', '--dataset1', type=str, help='Name of dataset1')
        parser.add_argument('-d2', '--dataset2', type=str, help='Name of dataset2')

    # assume directory is flat
    def handle(self, *args, **options):
        dataset1 = options.get('dataset1')
        dataset2 = options.get('dataset2')

        # Verify dataset names provided exist
        if dataset1 == None or dataset2 == None:
            raise CommandError("Please provide two dataset names.")
        verify_dataset_exists(dataset1)
        verify_dataset_exists(dataset2)

        bins = get_bins_in_datasets(dataset1, dataset2)
        rm_dataset = Dataset.objects.get(name=dataset1)
        print("Removing {} from the bins.".format(dataset1))
        for bin in bins:
            bin.datasets.remove(rm_dataset)
        
        print("Done!")
