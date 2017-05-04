#!/usr/bin/env bash
set -e

mkdir -p var
rm -rf .coverage
python -m coverage run --rcfile=.coveragerc ./test.py $1 --noinput
