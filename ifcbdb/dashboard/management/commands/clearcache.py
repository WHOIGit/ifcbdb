from django.core.management.base import BaseCommand, CommandError

from django.core.cache import cache

class Command(BaseCommand):

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        cache.clear()
