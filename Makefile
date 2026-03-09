PYTHON ?= python3

.PHONY: install test smoke intake-smoke verify-smoke run

install:
	$(PYTHON) -m pip install -e .[dev]

test:
	$(PYTHON) -m pytest

smoke:
	$(PYTHON) -m execution_accelerator --show-config

intake-smoke:
	$(PYTHON) -m execution_accelerator --bootstrap-ticket SEC-123 --thread-id sec-123-dev

verify-smoke:
	$(PYTHON) -m execution_accelerator --show-thread-state sec-123-dev

run:
	$(PYTHON) -m execution_accelerator
