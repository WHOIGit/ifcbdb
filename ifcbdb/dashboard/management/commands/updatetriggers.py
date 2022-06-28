from dashboard.models import Bin
from django.core.management.base import BaseCommand, CommandError
import csv
import os

class Command(BaseCommand):

    help = 'change labels'
    def add_arguments(self, parser):
        parser.add_argument('-i','--input', type=str, help='Path to csv of mapping of of bin ID and trigger count')

    def get_all_bins(self):   
        all = Bin.objects.all()
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

                for row in reader:
                    res = 0
                    res = Bin.objects.filter(pid=row[0]).update(n_triggers=row[1])
                    if res == 0:
                        print("Error: Bin, " + bin.pid + " not updated! Continuing ...")

    def handle(self, *args, **options):

        # handle arguments
        input_csv = options['input']
        # validate arguments
        if not input_csv:
            self.get_all_bins()
        else:
            print(input_csv)
            print(len(input_csv))
            self.parse_input_csv(input_csv)
        print("Done.")
        

    
