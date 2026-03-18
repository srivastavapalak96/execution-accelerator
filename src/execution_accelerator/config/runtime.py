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
    dry_run: bool
    keep_workspace: bool
    advisory_api_base_url: str
    maven_metadata_base_url: str
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
    dry_run = os.getenv("EA_DRY_RUN", "0") == "1"
    keep_workspace = os.getenv("EA_KEEP_WORKSPACE", "0") == "1"
    java_home_value = os.getenv("EA_JAVA_HOME")
    jira_fixture_path_value = os.getenv(
        "EA_JIRA_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "jira_issue.json"),
    )
    repository_inventory_fixture_path_value = os.getenv(
        "EA_REPOSITORY_INVENTORY_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "repository_inventory.json"),
    )
    advisory_fixture_path_value = os.getenv(
        "EA_ADVISORY_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "advisory_verification.json"),
    )
    maven_verification_fixture_path_value = os.getenv(
        "EA_MAVEN_VERIFICATION_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "maven_verification.json"),
    )
    pom_fixture_before_path_value = os.getenv(
        "EA_POM_FIXTURE_BEFORE_PATH",
        str(resolved_root / "tests" / "fixtures" / "pom_before.xml"),
    )
    pom_fixture_after_path_value = os.getenv(
        "EA_POM_FIXTURE_AFTER_PATH",
        str(resolved_root / "tests" / "fixtures" / "pom_after.xml"),
    )
    preflight_resolution_fixture_path_value = os.getenv(
        "EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "preflight_resolution.json"),
    )
    complex_artifact_fixture_path_value = os.getenv(
        "EA_COMPLEX_ARTIFACT_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "complex_artifacts.json"),
    )
    compatibility_diff_fixture_path_value = os.getenv(
        "EA_COMPATIBILITY_DIFF_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "compatibility_diff.json"),
    )
    decompiled_artifact_fixture_path_value = os.getenv(
        "EA_DECOMPILED_ARTIFACT_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "decompiled_artifacts.json"),
    )
    symbol_mapping_fixture_path_value = os.getenv(
        "EA_SYMBOL_MAPPING_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "symbol_mappings.json"),
    )
    code_change_plan_fixture_path_value = os.getenv(
        "EA_CODE_CHANGE_PLAN_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "code_change_plan.json"),
    )
    validation_result_fixture_path_value = os.getenv(
        "EA_VALIDATION_RESULT_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "validation_result.json"),
    )
    rollback_fixture_path_value = os.getenv(
        "EA_ROLLBACK_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "rollback_plan.json"),
    )
    branch_publication_fixture_path_value = os.getenv(
        "EA_BRANCH_PUBLICATION_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "branch_publication.json"),
    )
    pull_request_fixture_path_value = os.getenv(
        "EA_PULL_REQUEST_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "pull_request.json"),
    )
    jira_completion_fixture_path_value = os.getenv(
        "EA_JIRA_COMPLETION_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "jira_completion.json"),
    )

    return RuntimeConfig(
        repo_root=resolved_root,
        data_dir=data_dir,
        workspace_dir=workspace_dir,
        logs_dir=logs_dir,
        cache_dir=cache_dir,
        checkpoints_path=checkpoints_path,
        execution_mode=execution_mode,
        dry_run=dry_run,
        keep_workspace=keep_workspace,
        advisory_api_base_url=os.getenv("EA_OSV_API_BASE", "https://api.osv.dev"),
        maven_metadata_base_url=os.getenv("EA_MAVEN_METADATA_BASE", "https://repo1.maven.org/maven2"),
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
