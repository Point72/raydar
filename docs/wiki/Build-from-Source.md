`raydar` is written in Python and Javascript. While prebuilt wheels are provided for end users, it is also straightforward to build `raydar` from either the Python [source distribution](https://packaging.python.org/en/latest/specifications/source-distribution-format/) or the GitHub repository.

## Table of Contents

- [Table of Contents](#table-of-contents)
- [Make commands](#make-commands)
- [Prerequisites](#prerequisites)
- [Clone](#clone)
- [Install NodeJS](#install-nodejs)
- [Install Python dependencies](#install-python-dependencies)
- [Build](#build)
- [Lint and Autoformat](#lint-and-autoformat)
- [Testing](#testing)

## Make commands

As a convenience, `raydar` uses a `Makefile` for commonly used commands. You can print the main available commands by running `make` with no arguments

```bash
> make

build                          build the library
clean                          clean the repository
fix                            run autofixers
install                        install library
lint                           run lints
test                           run the tests
```

## Prerequisites

`raydar` has a few system-level dependencies which you can install from your machine package manager. Other package managers like `conda`, `nix`, etc, should also work fine.

## Clone

Clone the repo with:

```bash
git clone https://github.com/Point72/raydar.git
cd raydar
```

## Install NodeJS

Follow the instructions for [installing NodeJS](https://nodejs.org/en/download/package-manager/all) for your system. Once installed, you can [install `yarn`](https://classic.yarnpkg.com/lang/en/docs/install/) with:

```bash
npm instal --global yarn
```

## Install Python dependencies

Python build and develop dependencies are specified in the `pyproject.toml`, but you can manually install them:

```bash
make requirements

# or
# python -m pip install toml
# python -m pip install `python -c 'import toml; c = toml.load("pyproject.toml"); print("\n".join(c["build-system"]["requires"]))'`
# python -m pip install `python -c 'import toml; c = toml.load("pyproject.toml"); print("\n".join(c["project"]["optional-dependencies"]["develop"]))'`
```

Note that these dependencies would otherwise be installed normally as part of [PEP517](https://peps.python.org/pep-0517/) / [PEP518](https://peps.python.org/pep-0518/).

## Build

Build the python project in the usual manner:

```bash
make build

# on aarch64 linux, comment the above command and use this instead
# VCPKG_FORCE_SYSTEM_BINARIES=1 make build
# or
# python setup.py build build_ext --inplace
```

## Lint and Autoformat

`raydar` has linting and auto formatting.

| Language   | Linter     | Autoformatter | Description |
| :--------- | :--------- | :------------ | :---------- |
| Python     | `ruff`     | `ruff`        | Style       |
| Python     | `isort`    | `isort`       | Imports     |
| JavaScript | `prettier` | `prettier`    | Style       |
| Markdown   | `prettier` | `prettier`    | Style       |

**Python Linting**

```bash
make lintpy
# or
# python -m isort --check raydar/ setup.py
# python -m ruff check raydar/ setup.py
# python -m ruff format --check raydar/ setup.py
```

**Python Autoformatting**

```bash
make fixpy
# or
# python -m isort raydar/ setup.py
# python -m ruff format raydar/ setup.py
```

**JavaScript Linting**

```bash
make lintjs
# or
# cd js; yarn lint
```

**JavaScript Autoformatting**

```bash
make fixjs
# or
# cd js; yarn fix
```

**Documentation Linting**

We use `prettier` for our Markdown linting, so follow the above docs.

## Testing

`raydar` has both Python and JavaScript tests. The bulk of the functionality is tested in Python, which can be run via `pytest`. First, install the Python development dependencies with

```bash
make develop
```

**Python**

```bash
make testpy
# or
# python -m pytest -v raydar/tests --junitxml=junit.xml --cov=raydar --cov-report=xml:.coverage.xml --cov-branch --cov-fail-under=1 --cov-report term-missing
```

**JavaScript**

```bash
make testjs
# or
# cd js; yarn test
```
