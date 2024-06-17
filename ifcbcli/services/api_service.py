import requests
from django.conf import settings


class ApiService:
    @classmethod
    def search_bins(cls, dataset: str = None):
        body = {}

        if dataset:
            body['dataset'] = dataset

        return cls._get('/bins/search', body)

    @classmethod
    def list_datasets(cls):
        return cls._get('/datasets/')

    @classmethod
    def list_tags(cls):
        return cls._get('/tags/')

    # region " Helpers "

    @classmethod
    def _get(cls, path: str,  payload: dict = None) -> dict:
        return requests.get(settings.API_ENDPOINT + path, json=payload).json()

    @classmethod
    def _post(cls, path: str, payload: dict = None) -> dict:
        return requests.post(settings.API_ENDPOINT + path, json=payload).json()

    # endregion
