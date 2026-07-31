.PHONY: help all install compile-sass quality test covreport upgrade

help: ## display this help message
	@echo "Please use \`make <target>' where <target> is one of"
	@grep '^[a-zA-Z]' $(MAKEFILE_LIST) | sort | awk -F ':.*?## ' 'NF==2 {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}'

all: install compile-sass quality test

install: ## Install dev dependencies via uv
	uv sync --group dev

compile-sass:  ## Compile the Sass assets
	sass --no-cache --style compressed ./src/lti_consumer/static/sass/student.scss ./src/lti_consumer/static/css/student.css

quality:  ## Run the quality checks
	pycodestyle src/lti_consumer
	pylint --rcfile=pylintrc src/lti_consumer

test:  ## Run the tests
	mkdir -p var
	rm -rf .coverage
	python -m coverage run ./test.py --noinput
	python -m coverage xml

covreport:  ## Show the coverage results
	python -m coverage report -m --skip-covered

upgrade: ## Update uv.lock and regenerate uv constraints
	uv run --with edx-lint edx_lint write_uv_constraints pyproject.toml
	uv lock --upgrade


## Localization targets

WORKING_DIR := src/lti_consumer
EXTRACT_DIR := $(WORKING_DIR)/conf/locale/en/LC_MESSAGES
JS_COMPILE_DIR := $(WORKING_DIR)/public/js/translations
EXTRACTED_DJANGO_PARTIAL := $(EXTRACT_DIR)/django-partial.po
EXTRACTED_DJANGOJS_PARTIAL := $(EXTRACT_DIR)/djangojs-partial.po
EXTRACTED_DJANGO := $(EXTRACT_DIR)/django.po

extract_translations: ## extract strings to be translated, outputting .po files
	cd $(WORKING_DIR) && i18n_tool extract
	mv $(EXTRACTED_DJANGO_PARTIAL) $(EXTRACTED_DJANGO)
	# Safely concatenate djangojs if it exists
	if test -f $(EXTRACTED_DJANGOJS_PARTIAL); then \
	  msgcat $(EXTRACTED_DJANGO) $(EXTRACTED_DJANGOJS_PARTIAL) -o $(EXTRACTED_DJANGO) && \
	  rm $(EXTRACTED_DJANGOJS_PARTIAL); \
	fi
	sed -i'' -e 's/nplurals=INTEGER/nplurals=2/' $(EXTRACTED_DJANGO)
	sed -i'' -e 's/plural=EXPRESSION/plural=\(n != 1\)/' $(EXTRACTED_DJANGO)

compile_translations: ## compile translation files, outputting .mo files for each supported language
	cd $(WORKING_DIR) && i18n_tool generate
	python manage.py compilejsi18n --namespace XBlockLtiConsumerI18N --output $(JS_COMPILE_DIR)

detect_changed_source_translations:
	cd $(WORKING_DIR) && i18n_tool changed

dummy_translations: ## generate dummy translation (.po) files
	cd $(WORKING_DIR) && i18n_tool dummy

build_dummy_translations: dummy_translations compile_translations ## generate and compile dummy translation files

validate_translations: build_dummy_translations detect_changed_source_translations ## validate translations
