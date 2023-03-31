from collections import deque
import csv
import os
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from tqdm import tqdm
from tqdm._utils import _term_move_up

from dashboard.models import Bin, bin_query

class Command(BaseCommand):

    help = 'update triggers'

    border = "="*50
    clear_border = _term_move_up() + "\r" + " "*len(border) + "\r"

    def add_arguments(self, parser):
        parser.add_argument('-i','--input', type=str, help='Path to csv of mapping of of bin ID and trigger count')
        parser.add_argument('-d', '--dataset', type=str, help='Name of dataset to process(Optional)')

    def last_line(self, filename):
        d = deque(open(filename), 1)
        try:
            return d.pop()
        except IndexError:
            return None


    def n_triggers(self, line):
        if line is None:
            return 0
        return re.match(r'^(\d+)', line).group(0)

    def bulk_update(self, chunk, pbar):
        objs = []
        for bin in chunk:
            if not os.path.exists(bin.adc_path()):
                pbar.write(self.clear_border + ("Error: Bins, " + str(objs) + " not updated! Continuing ..."))
                pbar.write(self.border)
                continue
            bin.n_triggers = self.n_triggers(self.last_line(bin.adc_path()))
            objs.append(bin)
        res = Bin.objects.bulk_update(objs, ['n_triggers'])
        pbar.update(res)
        if res == 0:
            pbar.write(self.clear_border + ("Error: Bins, " + str(objs) + " not updated! Continuing ..."))
            pbar.write(self.border)


    def get_all_bins(self, dataset=None):
        count = bin_query(dataset_name=dataset).count()
        pbar = tqdm(total=count)

        # Bulk update 1000 bins at a time
        offset = 0
        limit = 1000
        partition = 1000

        while True:
            chunk = bin_query(dataset_name=dataset).order_by('pid')[offset:limit]
            chunk_length = len(chunk)
            if chunk_length < 1:
                break
            self.bulk_update(chunk, pbar)
            offset = limit
            limit = limit + partition


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
        

    
