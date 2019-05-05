from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Bin

class Command(BaseCommand):

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        bin = Bin.objects.order_by('?').first()
        print(bin.pid)
