#!/bin/bash

docker compose exec postgres pg_dump -U ifcb ifcb
