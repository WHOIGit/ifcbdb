import requests
from typing import List
from django.core.management.base import BaseCommand, CommandError
from pydantic import BaseModel, parse_obj_as
from core.schemas import DatasetSchema, TagSchema
from common import helpers


# TODO: Make into a common library/service?
class ApiService:
    @staticmethod
    def list_datasets():
        return requests.get('http://ifcbapi:8001/api/datasets/').json()

    @staticmethod
    def list_tags():
        return requests.get('http://ifcbapi:8001/api/tags/').json()


# TODO: Is there a better term for this than "query"? This can handle other entities as well, and shouldn't be strictly
#     :   limited to just datasets
class Command(BaseCommand):
    help = "TODO: Add help message"

    def add_arguments(self, parser):
        parser.add_argument("entity", choices=['datasets', 'tags'], type=str)

    def handle(self, *args, **options):
        response = ''

        match options['entity']:
            case 'datasets':
                datasets = ApiService.list_datasets()
                datasets = parse_obj_as(List[DatasetSchema], datasets)

                response = '\n'.join([x.name for x in datasets])
            case 'tags':
                tags = ApiService.list_tags()
                tags = parse_obj_as(List[TagSchema], tags)

                response = '\n'.join([x.name for x in tags])
            case _:
                # TODO: Should not happen because argument parser limits the values that can be submitted
                response = ''

        self.stdout.write(response)
