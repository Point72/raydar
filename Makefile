###############
# Build Tools #
###############
.PHONY: build develop install

build:  ## build python/javascript
	python -m build .

develop:  ## install to site-packages in editable mode
	python -m pip install --upgrade build pip setuptools toml twine wheel
	pip install `python -c 'import toml; c = toml.load("pyproject.toml"); print(" ".join(c["project"]["optional-dependencies"]["develop"]))'`
	cd js; yarn
	python -m pip install -e .[develop]

install:  ## install to site-packages
	python -m pip install .

###########
# Testing #
###########
.PHONY: testpy testjs test tests

testpy: ## Clean and Make unit tests
	python -m pytest -v raydar/tests --junitxml=junit.xml --cov=raydar --cov-report=xml:.coverage.xml --cov-branch --cov-fail-under=1 --cov-report term-missing

testjs: ## Clean and Make js tests
	cd js; yarn test

test: tests
tests: testpy testjs ## run the tests

###########
# Linting #
###########
.PHONY: lintpy lintjs lint fixpy fixjs fix format

lintpy:  ## Black/flake8 python
	python -m isort raydar setup.py --check
	python -m ruff check raydar setup.py
	python -m ruff format --check raydar setup.py

lintjs:  ## ESlint javascript
	cd js; yarn lint

lint: lintpy lintjs  ## run linter

fixpy:  ## Black python
	python -m isort raydar setup.py
	python -m ruff format raydar setup.py

fixjs:  ## ESlint Autofix JS
	cd js; yarn fix

fix: fixpy fixjs  ## run black/tslint fix
format: fix

#################
# Other Checks #
#################
.PHONY: check checks check-manifest

check: checks

checks: check-manifest  ## run security, packaging, and other checks

check-manifest:  ## run manifest checker for sdist
	check-manifest -v

################
# Distribution #
################
.PHONY: dist publishpy publishjs publish

dist: clean build  ## create dists
	python -m twine check dist/*

publishpy:  ## dist to pypi
	python -m twine upload dist/* --skip-existing

publishjs:  ## dist to npm
	cd js; npm publish || echo "can't publish - might already exist"

publish: dist publishpy publishjs  ## dist to pypi and npm

############
# Cleaning #
############
.PHONY: clean

clean: ## clean the repository
	find . -name "__pycache__" | xargs  rm -rf
	find . -name "*.pyc" | xargs rm -rf
	find . -name ".ipynb_checkpoints" | xargs  rm -rf
	rm -rf .coverage coverage *.xml build dist *.egg-info lib node_modules .pytest_cache *.egg-info
	rm -rf raydar/dashboard/static
	cd js && yarn clean
	git clean -fd

###########
# Helpers #
###########
.PHONY: help

# Thanks to Francoise at marmelab.com for this
.DEFAULT_GOAL := help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

print-%:
	@echo '$*=$($*)'

