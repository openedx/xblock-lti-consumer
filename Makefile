all: install compile-sass quality test

install-test:
	pip install -q -r test_requirements.txt

install: install-test

compile-sass:
	./scripts/sass.sh

quality:
	./scripts/quality.sh

test:
	./scripts/test.sh
