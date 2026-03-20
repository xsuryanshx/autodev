"""JSON-in / JSON-out driver for SubagentExecutor.

Used by:
- Claude Code slash command (Phase 5): ``python -m core.driver`` or ``python -c ...``
- Skill ``parallel-sandbox-executor``: stdin or file config
- CLI: ``python -m core run`` delegates here

Reads JSON config from stdin (default) or from ``--config`` path.
Writes JSON results to stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.sandbox_backend import SandboxConfig
from core.subagent_executor import AgentResult, SubagentExecutor, SubagentTask


def _serialize_agent_result(r: AgentResult) -> Dict[str, Any]:
    return {
        "task_id": r.task_id,
        "status": r.status,
        "output": r.output,
        "error": r.error,
        "files_created": r.files_created,
        "files_modified": r.files_modified,
        "duration_seconds": r.duration_seconds,
        "metadata": r.metadata,
    }


def run_tasks(
    config: Dict[str, Any],
    handler_registry: Optional[Dict[str, Callable]] = None,
) -> Dict[str, Any]:
    """Run subagent tasks from a config dict.

    Config keys:
    - ``workspace`` (str): base path for local sandboxes (default ``/tmp/autodev-workspace``)
    - ``max_parallelism`` (int): default 3
    - ``timeout_per_task`` (int): default 900
    - ``sandbox`` (dict): passed to ``SandboxConfig.from_dict``
    - ``tasks`` (list): each item has ``task_id``, ``description``, ``prompt``, ``skill``,
      optional ``timeout_seconds``, ``context``, ``metadata``
    - ``handlers`` (optional): not used from JSON — pass ``handler_registry`` from Python

    Returns:
        ``{"results": [...], "summary": {...}, "errors": []}``
    """
    workspace = config.get("workspace") or "/tmp/autodev-workspace"
    max_parallelism = int(config.get("max_parallelism", 3))
    timeout_per_task = int(config.get("timeout_per_task", 900))

    sandbox_cfg_dict = config.get("sandbox") or {}
    sandbox_config = SandboxConfig.from_dict(sandbox_cfg_dict)

    executor = SubagentExecutor(
        workspace=workspace,
        max_parallelism=max_parallelism,
        timeout_per_task=timeout_per_task,
        sandbox_config=sandbox_config,
    )

    handlers = dict(handler_registry or {})
    for skill, fn in handlers.items():
        executor.register_handler(skill, fn)

    if not handlers:
        try:
            from agents.subagent_handlers import CoderHandler, ResearcherHandler

            executor.register_handler("coder", CoderHandler().execute)
            executor.register_handler("researcher", ResearcherHandler().execute)
        except ImportError:

            def _stub_coder(ctx):
                return {"status": "completed", "message": "no handler registered"}

            executor.register_handler("coder", _stub_coder)

    tasks_raw = config.get("tasks") or []
    tasks: List[SubagentTask] = []
    for t in tasks_raw:
        tasks.append(
            SubagentTask(
                task_id=t["task_id"],
                description=t.get("description", ""),
                prompt=t.get("prompt", ""),
                skill=t["skill"],
                context=t.get("context"),
                timeout_seconds=int(t.get("timeout_seconds", timeout_per_task)),
                metadata=t.get("metadata") or {},
            )
        )

    errors: List[str] = []
    try:
        results = executor.submit_and_wait(tasks)
    finally:
        executor.shutdown(wait=True)

    serialized = [_serialize_agent_result(r) for r in results]
    completed = sum(1 for r in results if r.status == "completed")
    failed = sum(1 for r in results if r.status in ("failed", "timeout"))
    total_dur = sum(r.duration_seconds for r in results)

    summary = {
        "total": len(results),
        "completed": completed,
        "failed": failed,
        "total_duration_seconds": round(total_dur, 3),
    }

    return {
        "results": serialized,
        "summary": summary,
        "errors": errors,
    }


def load_config_from_stdin() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("No JSON on stdin")
    return json.loads(raw)


def load_config_from_path(path: str) -> Dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AutoDev sandbox driver (JSON in/out)")
    parser.add_argument(
        "--config",
        "-c",
        help="Path to JSON config file (if omitted, read JSON from stdin)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Write JSON results to this file instead of stdout",
    )
    args = parser.parse_args(argv)

    if args.config:
        config = load_config_from_path(args.config)
    else:
        config = load_config_from_stdin()

    out = run_tasks(config)
    all_ok = out["summary"]["failed"] == 0
    text = json.dumps(out, indent=2)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
