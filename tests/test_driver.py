"""Tests for core/driver.py."""
import json
import tempfile
from pathlib import Path

import pytest

from core.driver import main, run_tasks


def test_run_tasks_empty():
    out = run_tasks(
        {
            "workspace": tempfile.mkdtemp(),
            "tasks": [],
            "sandbox": {"backend": "local"},
        }
    )
    assert out["summary"]["total"] == 0
    assert out["summary"]["failed"] == 0


def test_run_tasks_one_coder():
    ws = tempfile.mkdtemp()
    out = run_tasks(
        {
            "workspace": ws,
            "max_parallelism": 1,
            "timeout_per_task": 60,
            "sandbox": {"backend": "local"},
            "tasks": [
                {
                    "task_id": "t1",
                    "description": "Test",
                    "prompt": "hello",
                    "skill": "coder",
                }
            ],
        }
    )
    assert len(out["results"]) == 1
    assert out["results"][0]["task_id"] == "t1"
    assert out["results"][0]["status"] == "completed"
    assert out["summary"]["failed"] == 0


def test_driver_main_json_file(tmp_path):
    cfg = {
        "workspace": str(tmp_path / "ws"),
        "tasks": [],
        "sandbox": {"backend": "local"},
    }
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg))
    out_path = tmp_path / "out.json"
    code = main(["--config", str(p), "--output", str(out_path)])
    assert code == 0
    data = json.loads(out_path.read_text())
    assert data["summary"]["total"] == 0


def test_driver_main_stdin(monkeypatch, tmp_path):
    cfg = {
        "workspace": str(tmp_path / "ws"),
        "tasks": [],
        "sandbox": {"backend": "local"},
    }
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(cfg)))
    out_path = tmp_path / "out.json"
    code = main(["--output", str(out_path)])
    assert code == 0
