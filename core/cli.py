"""CLI entry point: ``python -m core <subcommand>``."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.driver import load_config_from_path, run_tasks
from core.sandbox_backend import SandboxConfig
from core.sandbox_manager import SandboxManager


def _cmd_run(args: argparse.Namespace) -> int:
    if args.config:
        config = load_config_from_path(args.config)
    else:
        config = {}

    if args.tasks:
        tasks_path = Path(args.tasks)
        tasks_data = json.loads(tasks_path.read_text(encoding="utf-8"))
        if isinstance(tasks_data, dict) and "tasks" in tasks_data:
            tasks = tasks_data["tasks"]
        elif isinstance(tasks_data, list):
            tasks = tasks_data
        else:
            raise SystemExit("tasks file must be a list or {\"tasks\": [...]}")
    else:
        tasks = config.get("tasks") or []

    sandbox_cli: Dict[str, Any] = {
        "backend": args.backend,
        "timeout_seconds": args.timeout,
    }
    if args.repo:
        sandbox_cli["repo_url"] = args.repo
    if args.branch:
        sandbox_cli["branch"] = args.branch
    if args.clone_token:
        sandbox_cli["clone_token"] = args.clone_token
    elif os.environ.get("GITHUB_TOKEN"):
        sandbox_cli["clone_token"] = os.environ["GITHUB_TOKEN"]
    if args.e2b_template:
        sandbox_cli["e2b_template"] = args.e2b_template
    if args.e2b_api_key:
        sandbox_cli["e2b_api_key"] = args.e2b_api_key
    elif os.environ.get("E2B_API_KEY"):
        sandbox_cli["e2b_api_key"] = os.environ["E2B_API_KEY"]

    merged_sandbox = {**sandbox_cli, **config.get("sandbox", {})}
    if args.repo:
        merged_sandbox["repo_url"] = args.repo
    if args.branch:
        merged_sandbox["branch"] = args.branch

    config.setdefault("workspace", args.workspace)
    config.setdefault("max_parallelism", args.max_parallelism)
    config.setdefault("timeout_per_task", args.timeout)
    config["sandbox"] = merged_sandbox
    config["tasks"] = tasks

    out = run_tasks(config)
    text = json.dumps(out, indent=2)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)

    return 0 if out["summary"]["failed"] == 0 else 1


def _cmd_snapshot(args: argparse.Namespace) -> int:
    cfg = SandboxConfig(
        backend="e2b",
        e2b_template=args.e2b_template,
        e2b_api_key=args.e2b_api_key or os.environ.get("E2B_API_KEY"),
        timeout_seconds=args.timeout,
    )
    if not cfg.e2b_api_key:
        print("Error: E2B_API_KEY required for snapshot", file=sys.stderr)
        return 1

    mgr = SandboxManager(cfg)
    try:
        token = args.clone_token or os.environ.get("GITHUB_TOKEN")
        snap_id = mgr.create_warm_snapshot(
            repo_url=args.repo,
            branch=args.branch,
            clone_token=token,
        )
        result = {"snapshot_id": snap_id, "status": "success"}
        text = json.dumps(result, indent=2)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        return 1
    finally:
        mgr.shutdown()


def _cmd_status(_args: argparse.Namespace) -> int:
    info = {
        "active_sandboxes": [],
        "message": (
            "SandboxManager tracks sandboxes only inside the process that created them. "
            "Use `python -m core run --output results.json` to capture task results. "
            "For E2B dashboard state, see https://e2b.dev/docs"
        ),
    }
    print(json.dumps(info, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m core",
        description="AutoDev parallel sandbox executor CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Dispatch tasks and wait for JSON results")
    p_run.add_argument("--workspace", default="/tmp/autodev-workspace", help="Sandbox base directory")
    p_run.add_argument("--max-parallelism", type=int, default=3)
    p_run.add_argument("--timeout", type=int, default=900, help="Per-task timeout seconds")
    p_run.add_argument("--backend", default="local", choices=("local", "e2b"))
    p_run.add_argument("--repo", help="Git clone URL (triggers sandbox setup)")
    p_run.add_argument("--branch", help="Branch to checkout after clone")
    p_run.add_argument("--clone-token", help="Token for HTTPS clone (default: GITHUB_TOKEN env)")
    p_run.add_argument("--e2b-template", default="base")
    p_run.add_argument("--e2b-api-key", help="E2B API key (default: E2B_API_KEY env)")
    p_run.add_argument("--tasks", help="Path to tasks JSON file")
    p_run.add_argument("--config", "-c", help="Merge JSON config file (workspace, sandbox, tasks)")
    p_run.add_argument("--output", "-o", help="Write results JSON to file")
    p_run.set_defaults(func=_cmd_run)

    p_snap = sub.add_parser("snapshot", help="Create E2B warm snapshot (repo + deps)")
    p_snap.add_argument("--repo", required=True)
    p_snap.add_argument("--branch")
    p_snap.add_argument("--e2b-template", default="base")
    p_snap.add_argument("--e2b-api-key")
    p_snap.add_argument("--clone-token")
    p_snap.add_argument("--timeout", type=int, default=600)
    p_snap.add_argument("--output", "-o")
    p_snap.set_defaults(func=_cmd_snapshot)

    p_stat = sub.add_parser("status", help="Explain in-process sandbox tracking")
    p_stat.set_defaults(func=_cmd_status)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
