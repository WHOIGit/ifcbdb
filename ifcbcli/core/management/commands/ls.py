from typing import List
from pydantic import parse_obj_as
from django.core.management.base import BaseCommand, CommandError
from services import ApiService
from core.schemas import BinSchema
from common import helpers


class Command(BaseCommand):
    help = "TODO: Add help message"

    # TODO: Implement remaining criteria
    ALLOWED_PARAMETERS = ['dataset', 'instrument'] #, 'bin', 'sample-type', 'cruise', ]

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
        invalid_values = [v for v in options['criteria'] if not helpers.validate_query_parameter(v)]
        if len(invalid_values) > 0:
            helpers.write_error(
                self,
                'All criteria must be in the following format: param:value\n' +
                f'The following values are invalid: {invalid_values}'
            )
            return

        parameters = {}

        for criteria in options['criteria']:
            parameter, value = criteria.split(':')
            if parameter not in self.ALLOWED_PARAMETERS:
                helpers.write_error(self, f'Invalid parameter: {parameter}')
                return

            parameters[parameter] = value

        # TODO: Needs (much better) error handling using the HTTP code
        api_response = ApiService.search_bins(**parameters)

        if 'detail' in api_response:
            helpers.write_error(self, api_response['detail'])
            return

        # TODO: Needs error handling
        bins = parse_obj_as(List[BinSchema], api_response)
        bins = [x.pid for x in bins]

        self.stdout.write('\n'.join(bins))
