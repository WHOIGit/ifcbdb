from dashboard.models import Bin, bin_query
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from ifcb.data.stitching import InfilledImages
import csv
import os

class Command(BaseCommand):

    incorrect_instruments = ['IFCB1', 'IFCB5']
    help = 'get incorrect bins'
    def add_arguments(self, parser):
        parser.add_argument('-o','--output', type=str, help='Path to save csv of bin ID(s)')

    def request_get_instrument(instrument_string):
        i = instrument_string
        if i is not None and i:    
            if i.lower().startswith('ifcb'):
                i = i[4:]
            return int(i)

    def handle(self, *args, **options):
        output_path = options['output']
        # validate arguments
        if not output_path:
            raise CommandError('Output mapping folder path not specified')
        b_pids = []
        incorrect_instrument_num = []
        for instrument in self.incorrect_instruments:
            incorrect_instrument_num.append(self.request_get_instrument(instrument))
        if len(incorrect_instrument_num) == 0:
            raise CommandError('specified instruments do not exist')
        
        qs = Bin.objects
        # get bins in specified ifcb
        qs = qs.filter(instrument__number__in=incorrect_instrument_num)
        # get incorrect bins in specified ifcb
        for bin in qs:
            if len(bin.images) > len(InfilledImages(bin)):
                b_pids.append(bin.pid)
        # write to csv
        csv_file = output_path + 'incorrectbins.csv'
        with open(csv_file, 'w') as csvout:
            writer = csv.writer(csvout, lineterminator='\n')
            writer.writerows(all)
        print("List of bin id(s) in " + csv_file)
