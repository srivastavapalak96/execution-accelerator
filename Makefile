PYTHON ?= python3

.PHONY: install test smoke run

install:
	$(PYTHON) -m pip install -e .[dev]

test:
	$(PYTHON) -m pytest

smoke:
	$(PYTHON) -m execution_accelerator --show-config

run:
	$(PYTHON) -m execution_accelerator
