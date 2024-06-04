from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "TODO: Add help message"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=['add', 'remove'])

    def handle(self, *args, **options):
        action = options['action']

        self.stdout.write(
            self.style.SUCCESS(f'Successfully ran `tag` with argument {action}')
        )
