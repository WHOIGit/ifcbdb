from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Bin

class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('bin', type=str, help='bin id')
        parser.add_argument('tag', type=str, help='tag')

    def handle(self, *args, **options):
        bin_id = options['bin']
        tag = options['tag']
        bin = Bin.objects.get(pid=bin_id)
        bin.add_tag(tag)
        print(bin.tag_names)