from dashboard.models import Bin
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):

        all = Bin.objects.all()
        for bin in all:
            res = Bin.objects.filter(pid=bin.pid).update(n_triggers=bin._get_bin().n_triggers)
            if res == 0:
                print("Error: Bin, " + bin.pid + " not updated! Continuing ...")
        print("Done.")
