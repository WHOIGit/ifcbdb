#!/bin/bash

SOURCE=$(dirname "${BASH_SOURCE[0]}")
git pull && sh ${SOURCE}/assets.sh && sh ${SOURCE}/migrate.sh

