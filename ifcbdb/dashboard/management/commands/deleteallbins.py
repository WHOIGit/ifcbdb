from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Bin

class Command(BaseCommand):
    """for testing only!!"""
    
    help = 'delete all bins'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        Bin.objects.all().delete()
