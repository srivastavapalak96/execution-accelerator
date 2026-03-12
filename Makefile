PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

.PHONY: install test smoke intake-smoke verify-smoke remediate-smoke transitive-smoke complex-smoke validation-failure-smoke run

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

complex-smoke:
	EA_ADVISORY_FIXTURE_PATH=tests/fixtures/advisory_verification_complex.json \
	EA_MAVEN_VERIFICATION_FIXTURE_PATH=tests/fixtures/maven_verification_complex.json \
	EA_COMPLEX_ARTIFACT_FIXTURE_PATH=tests/fixtures/complex_artifacts.json \
	EA_COMPATIBILITY_DIFF_FIXTURE_PATH=tests/fixtures/compatibility_diff.json \
	EA_DECOMPILED_ARTIFACT_FIXTURE_PATH=tests/fixtures/decompiled_artifacts.json \
	EA_SYMBOL_MAPPING_FIXTURE_PATH=tests/fixtures/symbol_mappings.json \
	EA_CODE_CHANGE_PLAN_FIXTURE_PATH=tests/fixtures/code_change_plan.json \
	$(PYTHON) -m execution_accelerator --bootstrap-ticket SEC-123 --thread-id sec-123-complex
	EA_ADVISORY_FIXTURE_PATH=tests/fixtures/advisory_verification_complex.json \
	EA_MAVEN_VERIFICATION_FIXTURE_PATH=tests/fixtures/maven_verification_complex.json \
	EA_COMPLEX_ARTIFACT_FIXTURE_PATH=tests/fixtures/complex_artifacts.json \
	EA_COMPATIBILITY_DIFF_FIXTURE_PATH=tests/fixtures/compatibility_diff.json \
	EA_DECOMPILED_ARTIFACT_FIXTURE_PATH=tests/fixtures/decompiled_artifacts.json \
	EA_SYMBOL_MAPPING_FIXTURE_PATH=tests/fixtures/symbol_mappings.json \
	EA_CODE_CHANGE_PLAN_FIXTURE_PATH=tests/fixtures/code_change_plan.json \
	$(PYTHON) -m execution_accelerator --show-thread-state sec-123-complex

validation-failure-smoke:
	EA_VALIDATION_RESULT_FIXTURE_PATH=tests/fixtures/validation_result_failure.json \
	EA_ROLLBACK_FIXTURE_PATH=tests/fixtures/rollback_plan.json \
	$(PYTHON) -m execution_accelerator --bootstrap-ticket SEC-123 --thread-id sec-123-validation-failure
	EA_VALIDATION_RESULT_FIXTURE_PATH=tests/fixtures/validation_result_failure.json \
	EA_ROLLBACK_FIXTURE_PATH=tests/fixtures/rollback_plan.json \
	$(PYTHON) -m execution_accelerator --show-thread-state sec-123-validation-failure

run:
	$(PYTHON) -m execution_accelerator
