from django.core.management.base import BaseCommand, CommandError
from services import ApiService


class Command(BaseCommand):
    help = "TODO: Add help message"

    def handle(self, *args, **options):

        x = ApiService.update()

        self.stdout.write(
            self.style.WARNING('The "update" command has not been implemented yet.')
        )
