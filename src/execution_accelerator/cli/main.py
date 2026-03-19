"""Command line bootstrap for local development."""

from __future__ import annotations

import argparse
import os

from execution_accelerator.config import load_runtime_config
from execution_accelerator.graph import bootstrap_ticket_run, load_remediation_state, resume_ticket_run
from execution_accelerator.schemas import ApprovalDecision, HumanFeedback
from execution_accelerator.state import RemediationState
from execution_accelerator.observability import configure_logging
from execution_accelerator.version import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""

    parser = argparse.ArgumentParser(prog="execution-accelerator")
    parser.add_argument("--version", action="store_true", help="Print the application version and exit.")
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print resolved runtime directories for local development.",
    )
    parser.add_argument(
        "--bootstrap-ticket",
        metavar="TICKET_ID",
        help="Bootstrap a persisted remediation run for the provided Jira ticket id.",
    )
    parser.add_argument(
        "--thread-id",
        help="Override the LangGraph thread id used for checkpointed runs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Stop before publication side effects and leave the ticket in dry-run mode.",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Keep live-mode workspaces on disk after execution.",
    )
    parser.add_argument(
        "--workspace-dir",
        metavar="PATH",
        help="Override the workspace directory for this invocation.",
    )
    parser.add_argument(
        "--resume",
        metavar="THREAD_ID",
        help="Resume or rehydrate a persisted remediation thread.",
    )
    parser.add_argument(
        "--show-thread-state",
        metavar="THREAD_ID",
        help="Load and print the current persisted state summary for a LangGraph thread.",
    )
    parser.add_argument(
        "--approval-decision",
        choices=[ApprovalDecision.APPROVED, ApprovalDecision.REJECTED],
        help="Record a human approval decision while resuming a persisted thread.",
    )
    parser.add_argument(
        "--reviewer",
        help="Reviewer identity recorded alongside an approval decision.",
    )
    parser.add_argument(
        "--approval-comments",
        help="Optional comments recorded alongside an approval decision.",
    )
    return parser


def main() -> int:
    """CLI entrypoint."""

    parser = build_parser()
    args = parser.parse_args()
    previous_env = _apply_runtime_overrides(args)
    try:
        configure_logging()

        if args.version:
            print(__version__)
            return 0

        if args.show_config:
            config = load_runtime_config()
            print(f"repo_root={config.repo_root}")
            print(f"execution_mode={config.execution_mode}")
            print(f"dry_run={config.dry_run}")
            print(f"keep_workspace={config.keep_workspace}")
            print(f"data_dir={config.data_dir}")
            print(f"workspace_dir={config.workspace_dir}")
            print(f"logs_dir={config.logs_dir}")
            print(f"checkpoints_path={config.checkpoints_path}")
            print(f"jira_done_transition_id={config.jira_done_transition_id}")
            print(f"jira_done_status_name={config.jira_done_status_name}")
            print(f"jira_fixture_path={config.jira_fixture_path}")
            print(f"repository_inventory_fixture_path={config.repository_inventory_fixture_path}")
            print(f"advisory_fixture_path={config.advisory_fixture_path}")
            print(f"maven_verification_fixture_path={config.maven_verification_fixture_path}")
            print(f"pom_fixture_before_path={config.pom_fixture_before_path}")
            print(f"pom_fixture_after_path={config.pom_fixture_after_path}")
            print(f"preflight_resolution_fixture_path={config.preflight_resolution_fixture_path}")
            print(f"complex_artifact_fixture_path={config.complex_artifact_fixture_path}")
            print(f"compatibility_diff_fixture_path={config.compatibility_diff_fixture_path}")
            print(f"decompiled_artifact_fixture_path={config.decompiled_artifact_fixture_path}")
            print(f"symbol_mapping_fixture_path={config.symbol_mapping_fixture_path}")
            print(f"code_change_plan_fixture_path={config.code_change_plan_fixture_path}")
            print(f"validation_result_fixture_path={config.validation_result_fixture_path}")
            print(f"rollback_fixture_path={config.rollback_fixture_path}")
            print(f"branch_publication_fixture_path={config.branch_publication_fixture_path}")
            print(f"pull_request_fixture_path={config.pull_request_fixture_path}")
            print(f"jira_completion_fixture_path={config.jira_completion_fixture_path}")
            return 0

        if args.bootstrap_ticket:
            config = load_runtime_config()
            result = bootstrap_ticket_run(
                args.bootstrap_ticket,
                runtime_config=config,
                thread_id=args.thread_id,
            )
            _print_run_summary(
                thread_id=result.thread_id,
                checkpoint_path=str(result.checkpoint_path),
                state=result.state,
            )
            return 0

        if args.resume:
            config = load_runtime_config()
            result = resume_ticket_run(
                runtime_config=config,
                thread_id=args.resume,
                human_feedback=_build_human_feedback(args),
            )
            _print_run_summary(
                thread_id=result.thread_id,
                checkpoint_path=str(result.checkpoint_path),
                state=result.state,
            )
            return 0

        if args.show_thread_state:
            config = load_runtime_config()
            state = load_remediation_state(runtime_config=config, thread_id=args.show_thread_state)
            _print_run_summary(
                thread_id=args.show_thread_state,
                checkpoint_path=None,
                state=state,
            )
            return 0

        parser.print_help()
        return 0
    finally:
        _restore_runtime_overrides(previous_env)


def _apply_runtime_overrides(args: argparse.Namespace) -> dict[str, str | None]:
    previous_env = {
        "EA_WORKSPACE_DIR": os.environ.get("EA_WORKSPACE_DIR"),
        "EA_KEEP_WORKSPACE": os.environ.get("EA_KEEP_WORKSPACE"),
        "EA_DRY_RUN": os.environ.get("EA_DRY_RUN"),
    }
    if args.workspace_dir:
        os.environ["EA_WORKSPACE_DIR"] = args.workspace_dir
    if args.keep_workspace:
        os.environ["EA_KEEP_WORKSPACE"] = "1"
    if args.dry_run:
        os.environ["EA_DRY_RUN"] = "1"
    return previous_env


def _build_human_feedback(args: argparse.Namespace) -> HumanFeedback | None:
    if args.approval_decision is None:
        if args.reviewer or args.approval_comments:
            raise SystemExit("--reviewer and --approval-comments require --approval-decision.")
        return None
    if not args.resume:
        raise SystemExit("--approval-decision requires --resume.")
    return HumanFeedback(
        decision=ApprovalDecision(args.approval_decision),
        reviewer=args.reviewer,
        comments=args.approval_comments,
    )


def _restore_runtime_overrides(previous_env: dict[str, str | None]) -> None:
    for key, value in previous_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _print_run_summary(*, thread_id: str, checkpoint_path: str | None, state: RemediationState) -> None:
    print(f"thread_id={thread_id}")
    if checkpoint_path is not None:
        print(f"checkpoint_path={checkpoint_path}")
    print(f"workflow_status={state.workflow_status}")
    print(f"target_count={len(state.targets)}")
    print(f"current_target_index={state.current_target_index}")
    print(f"audit_event_count={len(state.audit_events)}")
    if state.vulnerability_details is not None:
        print(f"package_name={state.vulnerability_details.package_name}")
        print(f"severity={state.vulnerability_details.severity}")
    if state.advisory_verification is not None:
        print(f"recommended_fix_version={state.advisory_verification.recommended_fix_version}")
    if state.maven_verification is not None:
        print(f"dependency_kind={state.maven_verification.dependency_kind}")
    print(f"pending_repos={','.join(state.pending_repos)}")
    print(f"completed_repos={','.join(state.completed_repos)}")
    if state.route_decision is not None:
        print(f"route_strategy={state.route_decision.strategy}")
        print(f"route_confidence={state.route_decision.confidence:.2f}")
    if state.requires_human_approval:
        print(f"requires_human_approval={state.requires_human_approval}")
        print(f"approval_decision={state.human_approval_decision}")
        if state.human_feedback is not None and state.human_feedback.reviewer is not None:
            print(f"approval_reviewer={state.human_feedback.reviewer}")
    if state.remediation_plan is not None:
        print(f"plan_strategy={state.remediation_plan.strategy}")
    if state.pom_mutation_plan is not None and state.pom_mutation_plan.changes:
        change = state.pom_mutation_plan.changes[0]
        print(f"pom_change_kind={change.mutation_kind}")
        print(f"pom_change_target_section={change.target_section}")
    if state.complex_remediation_plan is not None:
        print(f"complex_candidate_count={len(state.complex_remediation_plan.artifact_candidates)}")
        print(
            "complex_breaking_change_count="
            f"{len(state.complex_remediation_plan.compatibility_diff.breaking_changes)}"
        )
    if state.code_change_plan is not None:
        print(f"complex_decompiled_artifact_count={len(state.decompiled_artifacts)}")
        print(f"complex_symbol_mapping_count={len(state.symbol_mappings)}")
        print(f"complex_planned_file_count={len(state.code_change_plan.target_files)}")
    if state.current_working_repo is not None:
        print(f"current_working_repo={state.current_working_repo}")
    print(f"modified_file_count={len(state.modified_files)}")
    if state.modified_files:
        print(f"modified_file={state.modified_files[0]}")
    if state.preflight_resolution is not None:
        print(f"preflight_status={state.preflight_resolution.status}")
        print(f"preflight_dependency_kind={state.preflight_resolution.dependency_kind}")
        print(f"preflight_resolved_version={state.preflight_resolution.resolved_version}")
    if state.validation_results:
        validation = state.validation_results[-1]
        print(f"validation_status={validation.status}")
        print(f"validation_check_count={len(validation.checks)}")
    if state.rollback_plan is not None:
        print(f"rollback_status={state.rollback_plan.status}")
        print(f"rollback_reason={state.rollback_plan.reason}")
    print(f"retry_count={state.retry_count}")
    if state.retry_decision is not None:
        print(f"retry_next_node={state.retry_decision.next_node}")
        print(f"retry_reason={state.retry_decision.reason}")
    if state.escalation_bundle is not None:
        print(f"escalation_bundle_path={state.escalation_bundle.bundle_path}")
    if state.branch_publication is not None:
        print(f"branch_name={state.branch_publication.branch_name}")
        print(f"branch_commit_sha={state.branch_publication.commit_sha}")
    if state.pull_request_summary is not None:
        print(f"pull_request_number={state.pull_request_summary.number}")
        print(f"pull_request_url={state.pull_request_summary.url}")
    if state.jira_completion is not None:
        print(f"jira_ticket_status={state.jira_completion.status}")
