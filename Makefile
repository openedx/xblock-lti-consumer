.PHONY: help all install-test install compile-sass quality test covreport upgrade

help: ## display this help message
	@echo "Please use \`make <target>' where <target> is one of"
	@grep '^[a-zA-Z]' $(MAKEFILE_LIST) | sort | awk -F ':.*?## ' 'NF==2 {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}'

all: install compile-sass quality test

install-test:
	pip install -q -r requirements/test.txt

install-dev:
	pip install -q -r requirements/dev.txt

install: install-test

compile-sass:  ## Compile the Sass assets
	sass --no-cache --style compressed ./lti_consumer/static/sass/student.scss ./lti_consumer/static/css/student.css

quality:  ## Run the quality checks
	pycodestyle --config=.pep8 lti_consumer
	pylint --rcfile=pylintrc lti_consumer
	python setup.py -q sdist
	twine check dist/*

test:  ## Run the tests
	mkdir -p var
	rm -rf .coverage
	python -m coverage run --rcfile=.coveragerc ./test.py --noinput

covreport:  ## Show the coverage results
	python -m coverage report -m --skip-covered

COMMON_CONSTRAINTS_TXT=requirements/common_constraints.txt
.PHONY: $(COMMON_CONSTRAINTS_TXT)
$(COMMON_CONSTRAINTS_TXT):
	wget -O "$(@)" https://raw.githubusercontent.com/edx/edx-lint/master/edx_lint/files/common_constraints.txt || touch "$(@)"

upgrade: export CUSTOM_COMPILE_COMMAND=make upgrade
upgrade: $(COMMON_CONSTRAINTS_TXT)  ## update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	pip install -q -r requirements/pip_tools.txt
	pip-compile --upgrade --allow-unsafe -o requirements/pip.txt requirements/pip.in
	pip-compile --upgrade -o requirements/pip_tools.txt requirements/pip_tools.in
	pip-compile --upgrade -o requirements/base.txt requirements/base.in
	pip-compile --upgrade -o requirements/dev.txt requirements/dev.in
	pip-compile --upgrade -o requirements/test.txt requirements/test.in
	pip-compile --upgrade -o requirements/tox.txt requirements/tox.in
	pip-compile --upgrade -o requirements/ci.txt requirements/ci.in
	pip-compile --upgrade -o requirements/quality.txt requirements/quality.in
	# Let tox control the Django version version for tests
	grep -e "^django==" requirements/test.txt > requirements/django.txt
	sed '/^[dD]jango==/d' requirements/test.txt > requirements/test.tmp
	mv requirements/test.tmp requirements/test.txt


## Localization targets

WORKING_DIR := lti_consumer
EXTRACT_DIR := $(WORKING_DIR)/translations/en/LC_MESSAGES
EXTRACTED_DJANGO := $(EXTRACT_DIR)/django-partial.po
EXTRACTED_DJANGOJS := $(EXTRACT_DIR)/djangojs-partial.po
EXTRACTED_TEXT := $(EXTRACT_DIR)/text.po

extract_translations: ## extract strings to be translated, outputting .po files
	cd $(WORKING_DIR) && i18n_tool extract
	mv $(EXTRACTED_DJANGO) $(EXTRACTED_TEXT)
	tail -n +20 $(EXTRACTED_DJANGOJS) >> $(EXTRACTED_TEXT)
	rm $(EXTRACTED_DJANGOJS)
	sed -i'' -e 's/nplurals=INTEGER/nplurals=2/' $(EXTRACTED_TEXT)
	sed -i'' -e 's/plural=EXPRESSION/plural=\(n != 1\)/' $(EXTRACTED_TEXT)

compile_translations: ## compile translation files, outputting .mo files for each supported language
	cd $(WORKING_DIR) && i18n_tool generate

detect_changed_source_translations:
	cd $(WORKING_DIR) && i18n_tool changed

dummy_translations: ## generate dummy translation (.po) files
	cd $(WORKING_DIR) && i18n_tool dummy

build_dummy_translations: dummy_translations compile_translations ## generate and compile dummy translation files

validate_translations: build_dummy_translations detect_changed_source_translations ## validate translations
