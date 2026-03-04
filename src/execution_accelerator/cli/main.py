"""Command line bootstrap for local development."""

from __future__ import annotations

import argparse

from execution_accelerator.config import load_runtime_config
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
        return 0

    parser.print_help()
    return 0
