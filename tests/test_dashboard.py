"""Tests for the dashboard server."""

import asyncio
import json
import os
import tempfile
import shutil

import pytest

from dashboard.server import DashboardServer, AIOHTTP_AVAILABLE


class TestDashboardServerInit:
    def test_default_port(self):
        server = DashboardServer()
        assert server.port == 8420

    def test_custom_port(self):
        server = DashboardServer(port=9999)
        assert server.port == 9999

    def test_default_events_path(self):
        server = DashboardServer()
        assert server.events_path == ".autodev/events.jsonl"

    def test_custom_events_path(self):
        server = DashboardServer(events_path="/tmp/test.jsonl")
        assert server.events_path == "/tmp/test.jsonl"


class TestSnapshotState:
    def test_initial_snapshot(self):
        server = DashboardServer()
        snap = server.get_snapshot()
        assert snap["session_id"] is None
        assert snap["phase"] is None
        assert snap["agents"] == {}
        assert snap["files"] == {}

    def test_session_start_updates_snapshot(self):
        server = DashboardServer()
        server.publish_event({
            "event_type": "session.start",
            "timestamp": "2026-03-20T06:00:00Z",
            "source": "orchestrator",
            "data": {"session_id": "abc123", "issue": "Test issue"},
        })
        snap = server.get_snapshot()
        assert snap["session_id"] == "abc123"
        assert snap["issue"] == "Test issue"
        assert snap["started_at"] == "2026-03-20T06:00:00Z"

    def test_phase_enter_updates_snapshot(self):
        server = DashboardServer()
        server.publish_event({
            "event_type": "phase.enter",
            "timestamp": "2026-03-20T06:01:00Z",
            "source": "orchestrator",
            "data": {"phase": 3},
        })
        snap = server.get_snapshot()
        assert snap["phase"] == 3

    def test_agent_dispatch_updates_snapshot(self):
        server = DashboardServer()
        server.publish_event({
            "event_type": "agent.dispatch",
            "timestamp": "2026-03-20T06:02:00Z",
            "source": "coder-1",
            "data": {
                "agent_id": "coder-1",
                "feature": "auth",
                "subtasks_total": 3,
            },
        })
        snap = server.get_snapshot()
        assert "coder-1" in snap["agents"]
        assert snap["agents"]["coder-1"]["status"] == "running"
        assert snap["agents"]["coder-1"]["subtasks_total"] == 3

    def test_agent_complete_updates_snapshot(self):
        server = DashboardServer()
        server.publish_event({
            "event_type": "agent.dispatch",
            "timestamp": "2026-03-20T06:02:00Z",
            "source": "coder-1",
            "data": {"agent_id": "coder-1"},
        })
        server.publish_event({
            "event_type": "agent.complete",
            "timestamp": "2026-03-20T06:05:00Z",
            "source": "coder-1",
            "data": {"agent_id": "coder-1"},
        })
        snap = server.get_snapshot()
        assert snap["agents"]["coder-1"]["status"] == "completed"

    def test_agent_error_updates_snapshot(self):
        server = DashboardServer()
        server.publish_event({
            "event_type": "agent.dispatch",
            "timestamp": "2026-03-20T06:02:00Z",
            "source": "coder-1",
            "data": {"agent_id": "coder-1"},
        })
        server.publish_event({
            "event_type": "agent.error",
            "timestamp": "2026-03-20T06:03:00Z",
            "source": "coder-1",
            "data": {"agent_id": "coder-1", "error": "timeout"},
        })
        snap = server.get_snapshot()
        assert snap["agents"]["coder-1"]["status"] == "error"
        assert snap["agents"]["coder-1"]["error"] == "timeout"

    def test_file_write_updates_snapshot(self):
        server = DashboardServer()
        server.publish_event({
            "event_type": "file.write",
            "timestamp": "2026-03-20T06:02:00Z",
            "source": "coder-1",
            "data": {"path": "src/auth.py", "agent_id": "coder-1"},
        })
        snap = server.get_snapshot()
        assert "src/auth.py" in snap["files"]
        assert "coder-1" in snap["files"]["src/auth.py"]

    def test_file_write_multi_agent_conflict(self):
        server = DashboardServer()
        server.publish_event({
            "event_type": "file.write",
            "source": "coder-1",
            "data": {"path": "src/config.py", "agent_id": "coder-1"},
        })
        server.publish_event({
            "event_type": "file.write",
            "source": "coder-2",
            "data": {"path": "src/config.py", "agent_id": "coder-2"},
        })
        snap = server.get_snapshot()
        assert len(snap["files"]["src/config.py"]) == 2

    def test_token_usage_accumulates(self):
        server = DashboardServer()
        server.publish_event({
            "event_type": "token.usage",
            "source": "coder-1",
            "data": {"model": "sonnet", "tokens": 1000, "cost": 0.01},
        })
        server.publish_event({
            "event_type": "token.usage",
            "source": "coder-2",
            "data": {"model": "sonnet", "tokens": 2000, "cost": 0.02},
        })
        snap = server.get_snapshot()
        assert snap["cost"]["total_tokens"] == 3000
        assert abs(snap["cost"]["total_cost"] - 0.03) < 0.001


class TestPublishEvent:
    def test_publish_without_clients(self):
        """Publishing with no SSE clients should not raise."""
        server = DashboardServer()
        server.publish_event({"event_type": "test", "data": {}})

    def test_snapshot_is_dict_copy(self):
        server = DashboardServer()
        snap1 = server.get_snapshot()
        snap1["session_id"] = "mutated"
        snap2 = server.get_snapshot()
        assert snap2["session_id"] is None


class TestEventsLogLoading:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.events_path = os.path.join(self.temp_dir, "events.jsonl")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_handle_missing_events_file(self):
        """Server should handle missing events file gracefully."""
        server = DashboardServer(events_path=os.path.join(self.temp_dir, "nonexistent.jsonl"))
        # Should not raise — events log endpoint handles missing file

    def test_static_dir_exists(self):
        """Verify STATIC_DIR points to actual directory."""
        from dashboard.server import STATIC_DIR
        assert STATIC_DIR.exists()
        assert (STATIC_DIR / "index.html").exists()


try:
    import pytest_asyncio
    HAS_PYTEST_ASYNCIO = True
except ImportError:
    HAS_PYTEST_ASYNCIO = False


@pytest.mark.skipif(
    not AIOHTTP_AVAILABLE or not HAS_PYTEST_ASYNCIO,
    reason="aiohttp or pytest-asyncio not installed",
)
class TestServerStartStop:
    def test_start_and_stop(self):
        loop = asyncio.new_event_loop()
        try:
            server = DashboardServer(port=18420)
            loop.run_until_complete(server.start())
            assert server._app is not None
            assert server._runner is not None
            loop.run_until_complete(server.stop())
            assert server._runner is None
        finally:
            loop.close()

    def test_snapshot_endpoint(self):
        from aiohttp.test_utils import TestClient, TestServer

        loop = asyncio.new_event_loop()
        try:
            server = DashboardServer(port=18421)
            app = __import__("aiohttp").web.Application()
            app.router.add_get("/api/snapshot", server._handle_snapshot)

            async def _run():
                async with TestClient(TestServer(app)) as client:
                    resp = await client.get("/api/snapshot")
                    assert resp.status == 200
                    data = await resp.json()
                    assert "session_id" in data
                    assert "agents" in data

            loop.run_until_complete(_run())
        finally:
            loop.close()
