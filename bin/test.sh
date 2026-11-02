#!/bin/bash

# No arguments: run the entire test suite. With arguments, they are passed
#   through as test labels (e.g. bin/test.sh api, or bin/test.sh api.tests.test_bins)

docker compose exec -T ifcbdb python manage.py test "$@" -v 2 \
  --testrunner ifcbdb.test_runner.QuietDbSetupRunner
