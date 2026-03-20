"""Tests for core/cli.py and python -m core."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from core.cli import build_parser, main


class TestCliParser:
    def test_run_subparser(self, tmp_path):
        tf = tmp_path / "t.json"
        tf.write_text('{"tasks":[]}')
        p = build_parser()
        args = p.parse_args(
            [
                "run",
                "--workspace",
                "/tmp/ws",
                "--backend",
                "local",
                "--tasks",
                str(tf),
            ]
        )
        assert args.command == "run"
        assert args.workspace == "/tmp/ws"

    def test_snapshot_subparser(self):
        p = build_parser()
        args = p.parse_args(
            [
                "snapshot",
                "--repo",
                "https://github.com/a/b.git",
                "--branch",
                "main",
            ]
        )
        assert args.command == "snapshot"
        assert args.repo == "https://github.com/a/b.git"


class TestCliStatus:
    def test_status_returns_zero(self):
        assert main(["status"]) == 0


class TestCliRunIntegration:
    def test_run_minimal_tasks_file(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "task_id": "cli-1",
                            "description": "d",
                            "prompt": "p",
                            "skill": "coder",
                        }
                    ]
                }
            )
        )
        out_file = tmp_path / "out.json"
        code = main(
            [
                "run",
                "--workspace",
                str(ws),
                "--backend",
                "local",
                "--tasks",
                str(tasks_file),
                "--output",
                str(out_file),
            ]
        )
        assert code == 0
        data = json.loads(out_file.read_text())
        assert data["results"][0]["status"] == "completed"


def test_python_m_core_status_subprocess():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "core", "status"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert "message" in data
