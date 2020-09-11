.PHONY: help all install-test install compile-sass quality test covreport upgrade

help: ## display this help message
	@echo "Please use \`make <target>' where <target> is one of"
	@grep '^[a-zA-Z]' $(MAKEFILE_LIST) | sort | awk -F ':.*?## ' 'NF==2 {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}'

all: install compile-sass quality test

install-test:
	pip install -q -r requirements/test.txt

install: install-test

compile-sass:  ## Compile the Sass assets
	sass --no-cache --style compressed ./lti_consumer/static/sass/student.scss ./lti_consumer/static/css/student.css

quality:  ## Run the quality checks
	pycodestyle --config=.pep8 lti_consumer
	pylint --rcfile=pylintrc lti_consumer

test:  ## Run the tests
	mkdir -p var
	rm -rf .coverage
	python -m coverage run --rcfile=.coveragerc ./test.py --noinput

covreport:  ## Show the coverage results
	python -m coverage report -m --skip-covered

upgrade: export CUSTOM_COMPILE_COMMAND=make upgrade
upgrade: ## update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	pip install -q -r requirements/pip_tools.txt
	pip-compile --upgrade -o requirements/pip_tools.txt requirements/pip_tools.in
	pip-compile --upgrade -o requirements/base.txt requirements/base.in
	pip-compile --upgrade -o requirements/test.txt requirements/test.in
	pip-compile --upgrade -o requirements/tox.txt requirements/tox.in
	pip-compile --upgrade -o requirements/travis.txt requirements/travis.in
	# Let tox control the Django version version for tests
	grep -e "^django==" requirements/test.txt > requirements/django.txt
	sed '/^[dD]jango==/d' requirements/test.txt > requirements/test.tmp
	mv requirements/test.tmp requirements/test.txt
