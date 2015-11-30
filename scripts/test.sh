#!/usr/bin/env bash
set -e

export DJANGO_SETTINGS_MODULE="workbench.settings"
mkdir -p var
rm -rf .coverage
nosetests --with-coverage --cover-package="lti_consumer"
