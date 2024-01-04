import os

IFCB_PASSWORD_KEY = 'ignore'

_HOST = os.getenv('NGINX_HOST', 'localhost')
_HTTPS_PORT = os.getenv('NGINX_HTTPS_PORT', '443')
_HTTP_PORT = os.getenv('NGINX_HTTP_PORT', '80')

ALLOWED_HOSTS = [_HOST]

CSRF_TRUSTED_ORIGINS = [f'https://{_HOST}:{_HTTPS_PORT}', f'http://{_HOST}:{_HTTP_PORT}']

DEFAULT_DATASET = os.getenv('DEFAULT_DATASET', '')