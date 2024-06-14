import requests
from typing import List
from pydantic import parse_obj_as
from django.core.management.base import BaseCommand, CommandError
from core.schemas import BinCriteriaSchema, BinSchema
from common import helpers


# TODO: Make into a common library/service?
class ApiService:
    @staticmethod
    def search_bins(dataset: str = None):
        body = {}

        if dataset:
            body['dataset'] = dataset

        return requests.get('http://ifcbapi:8001/api/bins/search', json=body).json()


class Command(BaseCommand):
    help = "TODO: Add help message"

    ALLOWED_PARAMETERS = ['dataset', 'instrument', 'bin', 'sample-type', 'cruise', ]

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

        # TODO: All of this logic is just a proof of concept and needs a lot of cleanup
        dataset = None

        for criteria in options['criteria']:
            parameter, value = criteria.split(':')
            if parameter not in self.ALLOWED_PARAMETERS:
                helpers.write_error(self, f'Invalid parameter: {parameter}')
                return

            match parameter:
                case 'dataset':
                    dataset = value
                case _:
                    helpers.write_error(self, f'The "{parameter}" parameter has not been implemented yet')
                    return

        # TODO: Needs (much better) error handling using the HTTP code
        api_response = ApiService.search_bins(dataset)

        if 'detail' in api_response:
            helpers.write_error(self, api_response['detail'])
            return

        # TODO: Needs error handling
        bins = parse_obj_as(List[BinSchema], api_response)
        bins = [x.pid for x in bins]

        self.stdout.write('\n'.join(bins))
