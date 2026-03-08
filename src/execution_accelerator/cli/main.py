"""Command line bootstrap for local development."""

from __future__ import annotations

import argparse

from execution_accelerator.config import load_runtime_config
from execution_accelerator.graph import bootstrap_ticket_run, load_remediation_state
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
        "--show-thread-state",
        metavar="THREAD_ID",
        help="Load and print the current persisted state summary for a LangGraph thread.",
    )
    return parser


def main() -> int:
    """CLI entrypoint."""

    parser = build_parser()
    args = parser.parse_args()
    configure_logging()

    if args.version:
        print(__version__)
        return 0

    if args.show_config:
        config = load_runtime_config()
        print(f"repo_root={config.repo_root}")
        print(f"data_dir={config.data_dir}")
        print(f"workspace_dir={config.workspace_dir}")
        print(f"logs_dir={config.logs_dir}")
        print(f"checkpoints_path={config.checkpoints_path}")
        print(f"jira_fixture_path={config.jira_fixture_path}")
        print(f"repository_inventory_fixture_path={config.repository_inventory_fixture_path}")
        return 0

    if args.bootstrap_ticket:
        config = load_runtime_config()
        result = bootstrap_ticket_run(
            args.bootstrap_ticket,
            runtime_config=config,
            thread_id=args.thread_id,
        )
        print(f"thread_id={result.thread_id}")
        print(f"checkpoint_path={result.checkpoint_path}")
        print(f"workflow_status={result.state.workflow_status}")
        print(f"audit_event_count={len(result.state.audit_events)}")
        if result.state.vulnerability_details is not None:
            print(f"package_name={result.state.vulnerability_details.package_name}")
            print(f"severity={result.state.vulnerability_details.severity}")
        print(f"pending_repos={','.join(result.state.pending_repos)}")
        if result.state.remediation_plan is not None:
            print(f"plan_strategy={result.state.remediation_plan.strategy}")
        return 0

    if args.show_thread_state:
        config = load_runtime_config()
        state = load_remediation_state(runtime_config=config, thread_id=args.show_thread_state)
        print(f"thread_id={args.show_thread_state}")
        print(f"workflow_status={state.workflow_status}")
        print(f"pending_repos={','.join(state.pending_repos)}")
        print(f"completed_repos={','.join(state.completed_repos)}")
        print(f"audit_event_count={len(state.audit_events)}")
        if state.vulnerability_details is not None:
            print(f"package_name={state.vulnerability_details.package_name}")
        return 0

    parser.print_help()
    return 0
