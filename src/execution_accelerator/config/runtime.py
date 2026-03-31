"""Runtime configuration primitives for local development."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from execution_accelerator.schemas import ExecutionMode


def _resolve_path_setting(value: str | Path, *, repo_root: Path) -> Path:
    """Resolve path settings relative to the repository root when needed."""

    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def _split_csv_setting(value: str | None) -> tuple[str, ...]:
    """Parse a comma-delimited environment setting into a normalized tuple."""

    if value is None:
        return ()
    return tuple(segment.strip() for segment in value.split(",") if segment.strip())


def _resolve_fixture_path_value(
    env_var: str,
    default_relative_path: str,
    *,
    execution_mode: ExecutionMode,
    repo_root: Path,
) -> str | None:
    """Resolve a fixture-path env var without silently defaulting in live mode."""

    configured_value = os.getenv(env_var)
    if configured_value is not None:
        return configured_value
    if execution_mode == ExecutionMode.LIVE:
        return None
    return str(repo_root / default_relative_path)


@dataclass(frozen=True)
class RuntimeConfig:
    """Resolved filesystem and environment settings for local execution."""

    repo_root: Path
    data_dir: Path
    workspace_dir: Path
    logs_dir: Path
    cache_dir: Path
    checkpoints_path: Path
    execution_mode: ExecutionMode
    max_retry_attempts: int
    dry_run: bool
    keep_workspace: bool
    advisory_api_base_url: str
    maven_metadata_base_url: str
    license_denylist: tuple[str, ...]
    license_allowlist: tuple[str, ...]
    java_home: Path | None
    jira_base_url: str | None
    jira_project_key: str | None
    jira_done_transition_id: str | None
    jira_done_status_name: str | None
    jira_fixture_path: Path | None
    repository_inventory_fixture_path: Path | None
    advisory_fixture_path: Path | None
    maven_verification_fixture_path: Path | None
    pom_fixture_before_path: Path | None
    pom_fixture_after_path: Path | None
    preflight_resolution_fixture_path: Path | None
    complex_artifact_fixture_path: Path | None
    compatibility_diff_fixture_path: Path | None
    decompiled_artifact_fixture_path: Path | None
    symbol_mapping_fixture_path: Path | None
    code_change_plan_fixture_path: Path | None
    validation_result_fixture_path: Path | None
    rollback_fixture_path: Path | None
    branch_publication_fixture_path: Path | None
    pull_request_fixture_path: Path | None
    jira_completion_fixture_path: Path | None
    github_owner: str | None


def load_runtime_config(repo_root: Path | None = None) -> RuntimeConfig:
    """Load runtime settings from the environment and sensible local defaults."""

    resolved_root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    data_dir = _resolve_path_setting(
        os.getenv("EA_DATA_DIR", resolved_root / ".local" / "data"),
        repo_root=resolved_root,
    )
    workspace_dir = _resolve_path_setting(
        os.getenv("EA_WORKSPACE_DIR", resolved_root / ".local" / "workspace"),
        repo_root=resolved_root,
    )
    logs_dir = _resolve_path_setting(
        os.getenv("EA_LOGS_DIR", resolved_root / ".local" / "logs"),
        repo_root=resolved_root,
    )
    cache_dir = _resolve_path_setting(
        os.getenv("EA_CACHE_DIR", resolved_root / ".local" / "cache"),
        repo_root=resolved_root,
    )
    checkpoints_path = _resolve_path_setting(
        os.getenv("EA_CHECKPOINTS_PATH", data_dir / "checkpoints.sqlite"),
        repo_root=resolved_root,
    )
    execution_mode = ExecutionMode(os.getenv("EA_MODE", ExecutionMode.FIXTURE))
    max_retry_attempts = resolve_max_retry_attempts()
    dry_run = os.getenv("EA_DRY_RUN", "0") == "1"
    keep_workspace = os.getenv("EA_KEEP_WORKSPACE", "0") == "1"
    java_home_value = os.getenv("EA_JAVA_HOME")
    jira_fixture_path_value = _resolve_fixture_path_value(
        "EA_JIRA_FIXTURE_PATH",
        "tests/fixtures/jira_issue.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    repository_inventory_fixture_path_value = _resolve_fixture_path_value(
        "EA_REPOSITORY_INVENTORY_FIXTURE_PATH",
        "tests/fixtures/repository_inventory.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    advisory_fixture_path_value = _resolve_fixture_path_value(
        "EA_ADVISORY_FIXTURE_PATH",
        "tests/fixtures/advisory_verification.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    maven_verification_fixture_path_value = _resolve_fixture_path_value(
        "EA_MAVEN_VERIFICATION_FIXTURE_PATH",
        "tests/fixtures/maven_verification.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    pom_fixture_before_path_value = _resolve_fixture_path_value(
        "EA_POM_FIXTURE_BEFORE_PATH",
        "tests/fixtures/pom_before.xml",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    pom_fixture_after_path_value = _resolve_fixture_path_value(
        "EA_POM_FIXTURE_AFTER_PATH",
        "tests/fixtures/pom_after.xml",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    preflight_resolution_fixture_path_value = _resolve_fixture_path_value(
        "EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH",
        "tests/fixtures/preflight_resolution.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    complex_artifact_fixture_path_value = _resolve_fixture_path_value(
        "EA_COMPLEX_ARTIFACT_FIXTURE_PATH",
        "tests/fixtures/complex_artifacts.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    compatibility_diff_fixture_path_value = _resolve_fixture_path_value(
        "EA_COMPATIBILITY_DIFF_FIXTURE_PATH",
        "tests/fixtures/compatibility_diff.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    decompiled_artifact_fixture_path_value = _resolve_fixture_path_value(
        "EA_DECOMPILED_ARTIFACT_FIXTURE_PATH",
        "tests/fixtures/decompiled_artifacts.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    symbol_mapping_fixture_path_value = _resolve_fixture_path_value(
        "EA_SYMBOL_MAPPING_FIXTURE_PATH",
        "tests/fixtures/symbol_mappings.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    code_change_plan_fixture_path_value = _resolve_fixture_path_value(
        "EA_CODE_CHANGE_PLAN_FIXTURE_PATH",
        "tests/fixtures/code_change_plan.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    validation_result_fixture_path_value = _resolve_fixture_path_value(
        "EA_VALIDATION_RESULT_FIXTURE_PATH",
        "tests/fixtures/validation_result.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    rollback_fixture_path_value = _resolve_fixture_path_value(
        "EA_ROLLBACK_FIXTURE_PATH",
        "tests/fixtures/rollback_plan.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    branch_publication_fixture_path_value = _resolve_fixture_path_value(
        "EA_BRANCH_PUBLICATION_FIXTURE_PATH",
        "tests/fixtures/branch_publication.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    pull_request_fixture_path_value = _resolve_fixture_path_value(
        "EA_PULL_REQUEST_FIXTURE_PATH",
        "tests/fixtures/pull_request.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )
    jira_completion_fixture_path_value = _resolve_fixture_path_value(
        "EA_JIRA_COMPLETION_FIXTURE_PATH",
        "tests/fixtures/jira_completion.json",
        execution_mode=execution_mode,
        repo_root=resolved_root,
    )

    return RuntimeConfig(
        repo_root=resolved_root,
        data_dir=data_dir,
        workspace_dir=workspace_dir,
        logs_dir=logs_dir,
        cache_dir=cache_dir,
        checkpoints_path=checkpoints_path,
        execution_mode=execution_mode,
        max_retry_attempts=max_retry_attempts,
        dry_run=dry_run,
        keep_workspace=keep_workspace,
        advisory_api_base_url=os.getenv("EA_OSV_API_BASE", "https://api.osv.dev"),
        maven_metadata_base_url=os.getenv("EA_MAVEN_METADATA_BASE", "https://repo1.maven.org/maven2"),
        license_denylist=_split_csv_setting(os.getenv("EA_LICENSE_DENYLIST")),
        license_allowlist=_split_csv_setting(os.getenv("EA_LICENSE_ALLOWLIST")),
        java_home=(
            _resolve_path_setting(java_home_value, repo_root=resolved_root)
            if java_home_value
            else None
        ),
        jira_base_url=os.getenv("EA_JIRA_BASE_URL"),
        jira_project_key=os.getenv("EA_JIRA_PROJECT_KEY"),
        jira_done_transition_id=os.getenv("EA_JIRA_DONE_TRANSITION_ID"),
        jira_done_status_name=os.getenv("EA_JIRA_DONE_STATUS_NAME"),
        jira_fixture_path=(
            _resolve_path_setting(jira_fixture_path_value, repo_root=resolved_root)
            if jira_fixture_path_value
            else None
        ),
        repository_inventory_fixture_path=(
            _resolve_path_setting(repository_inventory_fixture_path_value, repo_root=resolved_root)
            if repository_inventory_fixture_path_value
            else None
        ),
        advisory_fixture_path=(
            _resolve_path_setting(advisory_fixture_path_value, repo_root=resolved_root)
            if advisory_fixture_path_value
            else None
        ),
        maven_verification_fixture_path=(
            _resolve_path_setting(maven_verification_fixture_path_value, repo_root=resolved_root)
            if maven_verification_fixture_path_value
            else None
        ),
        pom_fixture_before_path=(
            _resolve_path_setting(pom_fixture_before_path_value, repo_root=resolved_root)
            if pom_fixture_before_path_value
            else None
        ),
        pom_fixture_after_path=(
            _resolve_path_setting(pom_fixture_after_path_value, repo_root=resolved_root)
            if pom_fixture_after_path_value
            else None
        ),
        preflight_resolution_fixture_path=(
            _resolve_path_setting(preflight_resolution_fixture_path_value, repo_root=resolved_root)
            if preflight_resolution_fixture_path_value
            else None
        ),
        complex_artifact_fixture_path=(
            _resolve_path_setting(complex_artifact_fixture_path_value, repo_root=resolved_root)
            if complex_artifact_fixture_path_value
            else None
        ),
        compatibility_diff_fixture_path=(
            _resolve_path_setting(compatibility_diff_fixture_path_value, repo_root=resolved_root)
            if compatibility_diff_fixture_path_value
            else None
        ),
        decompiled_artifact_fixture_path=(
            _resolve_path_setting(decompiled_artifact_fixture_path_value, repo_root=resolved_root)
            if decompiled_artifact_fixture_path_value
            else None
        ),
        symbol_mapping_fixture_path=(
            _resolve_path_setting(symbol_mapping_fixture_path_value, repo_root=resolved_root)
            if symbol_mapping_fixture_path_value
            else None
        ),
        code_change_plan_fixture_path=(
            _resolve_path_setting(code_change_plan_fixture_path_value, repo_root=resolved_root)
            if code_change_plan_fixture_path_value
            else None
        ),
        validation_result_fixture_path=(
            _resolve_path_setting(validation_result_fixture_path_value, repo_root=resolved_root)
            if validation_result_fixture_path_value
            else None
        ),
        rollback_fixture_path=(
            _resolve_path_setting(rollback_fixture_path_value, repo_root=resolved_root)
            if rollback_fixture_path_value
            else None
        ),
        branch_publication_fixture_path=(
            _resolve_path_setting(branch_publication_fixture_path_value, repo_root=resolved_root)
            if branch_publication_fixture_path_value
            else None
        ),
        pull_request_fixture_path=(
            _resolve_path_setting(pull_request_fixture_path_value, repo_root=resolved_root)
            if pull_request_fixture_path_value
            else None
        ),
        jira_completion_fixture_path=(
            _resolve_path_setting(jira_completion_fixture_path_value, repo_root=resolved_root)
            if jira_completion_fixture_path_value
            else None
        ),
        github_owner=os.getenv("EA_GITHUB_OWNER"),
    )


def resolve_max_retry_attempts() -> int:
    """Resolve the retry budget from the canonical env var or its deprecated alias."""

    value = os.getenv("EA_MAX_RETRIES")
    if value is None:
        value = os.getenv("EA_MAX_RETRY_ATTEMPTS", "3")
    return int(value)
