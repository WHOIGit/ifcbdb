from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "TODO: Add help message"

    def handle(self, *args, **options):

        self.stdout.write(
            self.style.WARNING('The "update" command has not been implemented yet.')
        )
