#!/usr/bin/env bash
set -e

pep8 --config=.pep8 lti_consumer
pylint --rcfile=pylintrc lti_consumer
