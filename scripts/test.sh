#!/usr/bin/env bash
set -e

mkdir -p var
rm -rf .coverage
python test.py $1 --noinput
