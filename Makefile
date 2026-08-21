#########
# BUILD #
#########
.PHONY: develop
develop:  ## setup project for development
	uv pip install -e .[develop]

.PHONY: requirements
requirements:  ## install prerequisite python build requirements
	python -m pip install --upgrade pip toml
	python -m pip install `python -c 'import toml; c = toml.load("pyproject.toml"); print("\n".join(c["build-system"]["requires"]))'`
	python -m pip install `python -c 'import toml; c = toml.load("pyproject.toml"); print(" ".join(c["project"]["optional-dependencies"]["develop"]))'`

.PHONY: build
build:  ## build the project
	python -m build -w -n

.PHONY: install
install:  ## install python library
	uv pip install .

#########
# LINTS #
#########
.PHONY: lint-py lint-docs lint lints
lint-py:  ## run python linter with ruff
	python -m ruff check raydar
	python -m ruff format --check raydar

lint-docs:  ## lint docs with mdformat and codespell
	python -m mdformat --check README.md docs/wiki/
	python -m codespell_lib README.md docs/wiki/

lint: lint-py lint-docs  ## run project linters

# alias
lints: lint

.PHONY: fix-py fix-docs fix format
fix-py:  ## fix python formatting with ruff
	python -m ruff check --fix raydar
	python -m ruff format raydar

fix-docs:  ## autoformat docs with mdformat and codespell
	python -m mdformat README.md docs/wiki/
	python -m codespell_lib --write README.md docs/wiki/

fix: fix-py fix-docs  ## run project autoformatters

# alias
format: fix

################
# Other Checks #
################
.PHONY: check-dist check-types checks check

check-dist:  ## check python sdist and wheel with check-dist
	check-dist -v

check-types:  ## check python types with ty
	ty check --python $$(which python)

checks: check-dist

# alias
check: checks

#########
# TESTS #
#########
.PHONY: test-py tests-py coverage-py
test-py:  ## run python tests
	python -m pytest -v raydar/tests

# alias
tests-py: test-py

coverage-py:  ## run python tests and collect test coverage
	python -m pytest -v raydar/tests --cov=raydar --cov-report term-missing --cov-report xml

.PHONY: test coverage tests
test: test-py  ## run all tests
coverage: coverage-py  ## run all tests and collect test coverage

# alias
tests: test

###########
# VERSION #
###########
.PHONY: show-version patch minor major

show-version:  ## show current library version
	@bump-my-version show current_version

patch:  ## bump a patch version
	@bump-my-version bump patch

minor:  ## bump a minor version
	@bump-my-version bump minor

major:  ## bump a major version
	@bump-my-version bump major

########
# DIST #
########
.PHONY: dist dist-py dist-check publish

dist-py:  ## build python dists
	python -m build -w -s

dist-check:  ## run python dist checker with twine
	python -m twine check dist/*

dist: clean build dist-py dist-check  ## build all dists

publish: dist  ## publish python assets

#########
# CLEAN #
#########
.PHONY: deep-clean clean

deep-clean: ## clean everything from the repository
	git clean -fdx

clean: ## clean the repository
	rm -rf .coverage coverage cover htmlcov logs build dist *.egg-info

############################################################################################

.PHONY: help

# Thanks to Francoise at marmelab.com for this
.DEFAULT_GOAL := help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

print-%:
	@echo '$*=$($*)'
