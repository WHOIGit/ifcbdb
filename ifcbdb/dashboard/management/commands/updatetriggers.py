from dashboard.models import Bin, bin_query
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import csv
import os

class Command(BaseCommand):

    help = 'change labels'
    def add_arguments(self, parser):
        parser.add_argument('-i','--input', type=str, help='Path to csv of mapping of of bin ID and trigger count')
        parser.add_argument('-d', '--dataset', type=str, help='Name of dataset to process')

    def get_all_bins(self, dataset=None):
        all = bin_query(dataset_name=dataset)
        for bin in all:
            res = Bin.objects.filter(pid=bin.pid).update(n_triggers=bin._get_bin().n_triggers)
            if res == 0:
                print("Error: Bin, " + bin.pid + " not updated! Continuing ...")

    def parse_input_csv(self, input_csv):
        if not os.path.exists(input_csv):
            raise CommandError('specified file does not exist')
        with open(input_csv,'r') as csvin:
            reader = csv.reader(csvin)
            row = next(reader)
            with transaction.atomic():
                for row in reader:
                    res = 0
                    res = Bin.objects.filter(pid=row[0]).update(n_triggers=row[1])
                    if res == 0:
                        print("Error: Bin, " + bin.pid + " not updated! Continuing ...")

    def handle(self, *args, **options):

        # handle arguments
        input_csv = options['input']
        dataset_name = options.get('dataset')
        # validate arguments
        if not input_csv:
            self.get_all_bins(dataset=dataset_name)
        else:
            self.parse_input_csv(input_csv)
        print("Done.")
        

    
