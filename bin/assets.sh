#!/bin/bash

docker exec -it ifcbdb python manage.py collectstatic --no-input
