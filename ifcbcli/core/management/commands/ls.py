from django.core.management.base import BaseCommand, CommandError
from common import helpers


# # TODO: Make into a common library/service?
# class ApiService:
#     @staticmethod
#     def list_datasets():
#         return requests.get('http://ifcbapi:8001/api/datasets/').json()
#


class Command(BaseCommand):
    help = "TODO: Add help message"

    def add_arguments(self, parser):
        parser.add_argument("criteria", nargs="+", type=str)

        # TODO: Implement
        parser.add_argument(
            "--format",
            choices=["json", "csv"],
            action="store",
            help="Output format which can be any of the following: csv, json",
        )

    def handle(self, *args, **options):
        criteria = options['criteria']

        invalid_values = [v for v in criteria if not helpers.validate_query_parameter(v)]
        if len(invalid_values) > 0:
            self.stdout.write(
                self.style.ERROR(
                    'All criteria must be in the following format: param:value\n' +
                    f'The following values are invalid: {invalid_values}'
                )
            )
            return

        # TODO: Implement allowed parameter names
        allowed_parameters = ['dataset', 'instrument', 'bin', 'sample-type', 'cruise', ]

        print('criteria: ', criteria)
        print('format', options['format'])

        self.stdout.write(
            self.style.SUCCESS('Successfully ran `ls`')
        )
