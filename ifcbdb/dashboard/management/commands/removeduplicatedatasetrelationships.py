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
        parser.add_argument('-r', '--remove', type=str, help='Name of dataset to remove from bins')
        parser.add_argument('-k', '--keep', type=str, help='Name of dataset to keep in bins')


    # assume directory is flat
    def handle(self, *args, **options):
        dataset_to_remove = options.get('remove')
        dataset_to_keep = options.get('keep')

        # Verify dataset names provided exist
        if dataset_to_remove == None or dataset_to_keep == None:
            raise CommandError("Please provide two dataset names.")
        if dataset_to_remove == dataset_to_keep:
            raise CommandError("Please provide two different dataset names.")
        verify_dataset_exists(dataset_to_remove)
        verify_dataset_exists(dataset_to_keep)

        bins = get_bins_in_datasets(dataset_to_keep, dataset_to_remove)
        rm_dataset = Dataset.objects.get(name=dataset_to_remove)
        print("Removing {} from the bins.".format(dataset_to_remove))
        for bin in bins:
            bin.datasets.remove(rm_dataset)
        
        print("Done!")
