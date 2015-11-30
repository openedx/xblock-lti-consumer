#!/usr/bin/env bash
set -e

# Student view sass
sass --no-cache --style compressed ./lti_consumer/static/sass/student.scss ./lti_consumer/static/css/student.css
