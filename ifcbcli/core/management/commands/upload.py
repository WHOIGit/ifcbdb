from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "TODO: Add help message"

    # def add_arguments(self, parser):
    #     parser.add_argument("poll_ids", nargs="+", type=int)

    def handle(self, *args, **options):

        self.stdout.write(
            self.style.WARNING('The "upload" command has not been implemented yet.')
        )
