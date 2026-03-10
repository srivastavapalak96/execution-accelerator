PYTHON ?= python3

.PHONY: install test smoke intake-smoke verify-smoke remediate-smoke transitive-smoke run

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

remediate-smoke:
	$(PYTHON) -m execution_accelerator --bootstrap-ticket SEC-123 --thread-id sec-123-remediate
	$(PYTHON) -m execution_accelerator --show-thread-state sec-123-remediate

transitive-smoke:
	EA_MAVEN_VERIFICATION_FIXTURE_PATH=tests/fixtures/maven_verification_transitive.json \
	EA_POM_FIXTURE_BEFORE_PATH=tests/fixtures/pom_transitive_before.xml \
	EA_POM_FIXTURE_AFTER_PATH=tests/fixtures/pom_transitive_after.xml \
	EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH=tests/fixtures/preflight_resolution_transitive.json \
	$(PYTHON) -m execution_accelerator --bootstrap-ticket SEC-123 --thread-id sec-123-transitive
	EA_MAVEN_VERIFICATION_FIXTURE_PATH=tests/fixtures/maven_verification_transitive.json \
	EA_POM_FIXTURE_BEFORE_PATH=tests/fixtures/pom_transitive_before.xml \
	EA_POM_FIXTURE_AFTER_PATH=tests/fixtures/pom_transitive_after.xml \
	EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH=tests/fixtures/preflight_resolution_transitive.json \
	$(PYTHON) -m execution_accelerator --show-thread-state sec-123-transitive

run:
	$(PYTHON) -m execution_accelerator
