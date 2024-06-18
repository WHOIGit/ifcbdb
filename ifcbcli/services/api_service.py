import requests
from django.conf import settings


class ApiService:
    @classmethod
    def search_bins(cls, dataset: str = None, instrument: int = None):
        body = {}

        if dataset:
            body['dataset'] = dataset

        if instrument:
            body['instrument'] = instrument

        return cls._get('/bins/search', body)

    @classmethod
    def list_datasets(cls):
        return cls._get('/datasets/')

    @classmethod
    def list_tags(cls):
        return cls._get('/tags/')

    # TODO: Nothing is implemented here except the authentication mechanism
    @classmethod
    def update(cls):
        # TODO: Implement error handling (in _get and _post calls)
        return cls._get('/management/update/')
        # try:
        #     return cls._get('/management/update/')
        # except requests.exceptions.HTTPError as http_error:
        #     print(http_error)

    # region " Helpers "

    @classmethod
    def _get(cls, path: str,  payload: dict = None) -> dict:
        return requests.get(settings.API_ENDPOINT + path, json=payload).json()

    @classmethod
    def _post(cls, path: str, payload: dict = None) -> dict:
        return requests.post(settings.API_ENDPOINT + path, json=payload).json()

    # endregion
