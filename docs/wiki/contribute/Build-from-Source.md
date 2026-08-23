`raydar` is written in Python. While prebuilt wheels are provided for end users, it is also straightforward to build `raydar` from either the Python [source distribution](https://packaging.python.org/en/latest/specifications/source-distribution-format/) or the GitHub repository.

- [Make commands](#make-commands)
- [Prerequisites](#prerequisites)
- [Clone](#clone)
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

## Install Python dependencies

Python build and develop dependencies are specified in the `pyproject.toml`, but you can manually install them:

```bash
make requirements
```

Note that these dependencies would otherwise be installed normally as part of [PEP517](https://peps.python.org/pep-0517/) / [PEP518](https://peps.python.org/pep-0518/).

## Build

Build the python project in the usual manner:

```bash
make build
```

## Lint and Autoformat

`raydar` has linting and auto formatting.

| Language | Linter      | Autoformatter | Description |
| :------- | :---------- | :------------ | :---------- |
| Python   | `ruff`      | `ruff`        | Style       |
| Markdown | `mdformat`  | `mdformat`    | Style       |
| Markdown | `codespell` |               | Spelling    |

**Python Linting**

```bash
make lint-py
```

**Python Autoformatting**

```bash
make fix-py
```

**Documentation Linting**

```bash
make lint-docs
```

**Documentation Autoformatting**

```bash
make fix-docs
```

## Testing

`raydar` has extensive Python tests. The tests can be run via `pytest`. First, install the Python development dependencies with

```bash
make develop
```

**Python**

```bash
make test
```
