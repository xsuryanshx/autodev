"""
tests/test_telemetry.py — Comprehensive tests for core/telemetry.py.

Covers:
- phase_context: duration tracking and enter/exit event emission
- record_agent_dispatch / record_agent_result: agent lifecycle
- record_token_usage: token counts and cost calculation
- get_phase_summary: per-phase metrics retrieval
- get_session_summary: full-session aggregation
- Multiple independent phases
- Mock EventEmitter to assert events emitted
"""

from __future__ import annotations

import time
from typing import List
from unittest.mock import MagicMock, call, patch

import pytest

from core.events import AgentEvent, EventEmitter
from core.telemetry import PipelineTelemetry, _cost_usd


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


class CapturingEmitter(EventEmitter):
    """An EventEmitter that stores every emitted event for assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.emitted: List[AgentEvent] = []
        self.subscribe(self.emitted.append)


@pytest.fixture
def emitter() -> CapturingEmitter:
    return CapturingEmitter()


@pytest.fixture
def tel(emitter: CapturingEmitter) -> PipelineTelemetry:
    return PipelineTelemetry(emitter, session_id="test-session-001")


# ---------------------------------------------------------------------------
# Cost helper
# ---------------------------------------------------------------------------


class TestCostEstimation:
    def test_sonnet_cost(self):
        cost = _cost_usd("sonnet", 1_000_000, 1_000_000)
        assert cost == pytest.approx(18.0)

    def test_haiku_cost(self):
        cost = _cost_usd("haiku", 1_000_000, 1_000_000)
        assert cost == pytest.approx(1.5)

    def test_opus_cost(self):
        cost = _cost_usd("opus", 1_000_000, 1_000_000)
        assert cost == pytest.approx(90.0)

    def test_unknown_model_zero_cost(self):
        cost = _cost_usd("unknown-model-v99", 500_000, 500_000)
        assert cost == pytest.approx(0.0)

    def test_zero_tokens_zero_cost(self):
        cost = _cost_usd("sonnet", 0, 0)
        assert cost == pytest.approx(0.0)

    def test_model_name_case_insensitive(self):
        cost_lower = _cost_usd("sonnet", 100_000, 50_000)
        cost_upper = _cost_usd("Sonnet", 100_000, 50_000)
        assert cost_lower == pytest.approx(cost_upper)


# ---------------------------------------------------------------------------
# EventEmitter basics
# ---------------------------------------------------------------------------


class TestEventEmitter:
    def test_subscribe_and_receive(self):
        emitter = CapturingEmitter()
        event = AgentEvent(
            event_type="test.event",
            timestamp="2026-01-01T00:00:00+00:00",
            source="test",
            phase=1,
            data={},
            session_id="s1",
        )
        emitter.emit(event)
        assert len(emitter.emitted) == 1
        assert emitter.emitted[0].event_type == "test.event"

    def test_multiple_subscribers_all_notified(self):
        emitter = EventEmitter()
        received_a: List[AgentEvent] = []
        received_b: List[AgentEvent] = []
        emitter.subscribe(received_a.append)
        emitter.subscribe(received_b.append)

        event = AgentEvent("x", "ts", "src", 0, {}, "s1")
        emitter.emit(event)

        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_misbehaving_subscriber_does_not_break_pipeline(self):
        emitter = EventEmitter()

        def bad_sub(event: AgentEvent) -> None:
            raise RuntimeError("boom")

        received: List[AgentEvent] = []
        emitter.subscribe(bad_sub)
        emitter.subscribe(received.append)

        emitter.emit(AgentEvent("x", "ts", "src", 0, {}, "s1"))
        assert len(received) == 1


# ---------------------------------------------------------------------------
# phase_context
# ---------------------------------------------------------------------------


class TestPhaseContext:
    def test_phase_context_tracks_duration(self, tel, emitter):
        with tel.phase_context(1, "parse"):
            time.sleep(0.1)

        summary = tel.get_phase_summary(1)
        assert "duration_seconds" in summary
        assert summary["duration_seconds"] >= 0.1

    def test_phase_context_emits_enter_event(self, tel, emitter):
        with tel.phase_context(2, "validate"):
            pass

        enter_events = [e for e in emitter.emitted if e.event_type == "phase.enter"]
        assert len(enter_events) == 1
        assert enter_events[0].phase == 2
        assert enter_events[0].data["phase_name"] == "validate"
        assert enter_events[0].session_id == "test-session-001"

    def test_phase_context_emits_exit_event(self, tel, emitter):
        with tel.phase_context(3, "explore"):
            pass

        exit_events = [e for e in emitter.emitted if e.event_type == "phase.exit"]
        assert len(exit_events) == 1
        assert exit_events[0].phase == 3
        assert exit_events[0].data["phase_name"] == "explore"
        assert "duration_seconds" in exit_events[0].data

    def test_phase_context_enter_before_exit(self, tel, emitter):
        with tel.phase_context(1, "parse"):
            pass

        types = [e.event_type for e in emitter.emitted]
        assert types.index("phase.enter") < types.index("phase.exit")

    def test_phase_context_yields_metrics_dict(self, tel, emitter):
        with tel.phase_context(4, "plan") as metrics:
            metrics["features_count"] = 3
            metrics["subtasks_count"] = 9

        summary = tel.get_phase_summary(4)
        assert summary["features_count"] == 3
        assert summary["subtasks_count"] == 9

    def test_phase_context_exit_emitted_on_exception(self, tel, emitter):
        with pytest.raises(ValueError):
            with tel.phase_context(1, "parse"):
                raise ValueError("test error")

        exit_events = [e for e in emitter.emitted if e.event_type == "phase.exit"]
        assert len(exit_events) == 1

    def test_multiple_phases_tracked_independently(self, tel, emitter):
        with tel.phase_context(1, "parse") as m1:
            m1["issue_type"] = "bug"
            time.sleep(0.05)

        with tel.phase_context(2, "validate") as m2:
            m2["decision"] = "VALID"
            time.sleep(0.05)

        s1 = tel.get_phase_summary(1)
        s2 = tel.get_phase_summary(2)

        assert s1["issue_type"] == "bug"
        assert s2["decision"] == "VALID"
        assert s1["phase_name"] == "parse"
        assert s2["phase_name"] == "validate"
        assert s1["duration_seconds"] >= 0.05
        assert s2["duration_seconds"] >= 0.05

    def test_get_phase_summary_unknown_phase_returns_empty(self, tel):
        result = tel.get_phase_summary(99)
        assert result == {}


# ---------------------------------------------------------------------------
# Agent dispatch / result
# ---------------------------------------------------------------------------


class TestAgentTracking:
    def test_record_agent_dispatch(self, tel, emitter):
        tel.record_agent_dispatch("task-1", "implement", "feat-1")

        dispatch_events = [e for e in emitter.emitted if e.event_type == "agent.dispatch"]
        assert len(dispatch_events) == 1
        assert dispatch_events[0].data["task_id"] == "task-1"
        assert dispatch_events[0].data["skill"] == "implement"
        assert dispatch_events[0].data["feature_id"] == "feat-1"

    def test_record_agent_result(self, tel, emitter):
        tel.record_agent_dispatch("task-2", "implement", "feat-2")
        tel.record_agent_result(
            "task-2",
            "success",
            files_created=["new_module.py"],
            files_modified=["existing.py"],
        )

        result_events = [e for e in emitter.emitted if e.event_type == "agent.result"]
        assert len(result_events) == 1
        data = result_events[0].data
        assert data["task_id"] == "task-2"
        assert data["status"] == "success"
        assert "new_module.py" in data["files_created"]
        assert "existing.py" in data["files_modified"]

    def test_record_agent_result_without_prior_dispatch(self, tel, emitter):
        # Should not raise even without a prior dispatch record.
        tel.record_agent_result("orphan-task", "failed", [], [])
        result_events = [e for e in emitter.emitted if e.event_type == "agent.result"]
        assert len(result_events) == 1

    def test_agent_result_stored_in_session_summary(self, tel, emitter):
        tel.record_agent_dispatch("task-3", "test_write", "feat-3")
        tel.record_agent_result("task-3", "success", ["test_foo.py"], [])

        summary = tel.get_session_summary()
        assert "task-3" in summary["agents"]
        agent = summary["agents"]["task-3"]
        assert agent["status"] == "success"
        assert "test_foo.py" in agent["files_created"]

    def test_multiple_agents_tracked_independently(self, tel, emitter):
        tel.record_agent_dispatch("t1", "implement", "f1")
        tel.record_agent_dispatch("t2", "implement", "f2")
        tel.record_agent_result("t1", "success", ["a.py"], [])
        tel.record_agent_result("t2", "failed", [], [])

        summary = tel.get_session_summary()
        assert summary["agents"]["t1"]["status"] == "success"
        assert summary["agents"]["t2"]["status"] == "failed"


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_record_token_usage_emits_event(self, tel, emitter):
        tel.record_token_usage("task-4", 1000, 500, "sonnet")

        token_events = [e for e in emitter.emitted if e.event_type == "agent.token_usage"]
        assert len(token_events) == 1
        data = token_events[0].data
        assert data["task_id"] == "task-4"
        assert data["input_tokens"] == 1000
        assert data["output_tokens"] == 500
        assert data["model"] == "sonnet"

    def test_record_token_usage_calculates_cost(self, tel, emitter):
        # 1 000 000 input tokens at $3/M + 500 000 output at $15/M = $3 + $7.50 = $10.50
        tel.record_token_usage("task-5", 1_000_000, 500_000, "sonnet")

        summary = tel.get_session_summary()
        agent = summary["agents"]["task-5"]
        assert agent["cost_usd"] == pytest.approx(10.50)

    def test_record_token_usage_haiku_pricing(self, tel, emitter):
        # 2 000 000 input at $0.25/M + 1 000 000 output at $1.25/M = $0.50 + $1.25 = $1.75
        tel.record_token_usage("task-6", 2_000_000, 1_000_000, "haiku")

        summary = tel.get_session_summary()
        assert summary["agents"]["task-6"]["cost_usd"] == pytest.approx(1.75)

    def test_total_cost_aggregated_in_session_summary(self, tel, emitter):
        tel.record_token_usage("ta", 1_000_000, 0, "haiku")   # $0.25
        tel.record_token_usage("tb", 0, 1_000_000, "haiku")   # $1.25
        summary = tel.get_session_summary()
        assert summary["total_cost_usd"] == pytest.approx(1.50)

    def test_total_token_counts_aggregated(self, tel, emitter):
        tel.record_token_usage("t1", 100, 200, "sonnet")
        tel.record_token_usage("t2", 300, 400, "sonnet")
        summary = tel.get_session_summary()
        assert summary["total_input_tokens"] == 400
        assert summary["total_output_tokens"] == 600


# ---------------------------------------------------------------------------
# Session summary
# ---------------------------------------------------------------------------


class TestSessionSummary:
    def test_session_summary_includes_session_id(self, tel, emitter):
        summary = tel.get_session_summary()
        assert summary["session_id"] == "test-session-001"

    def test_session_summary_aggregates_file_counts(self, tel, emitter):
        tel.record_agent_dispatch("t1", "implement", "f1")
        tel.record_agent_result("t1", "success", ["a.py", "b.py"], ["c.py"])
        tel.record_agent_dispatch("t2", "implement", "f2")
        tel.record_agent_result("t2", "success", ["d.py"], ["e.py", "f.py"])

        summary = tel.get_session_summary()
        assert set(summary["total_files_created"]) == {"a.py", "b.py", "d.py"}
        assert set(summary["total_files_modified"]) == {"c.py", "e.py", "f.py"}

    def test_session_summary_total_duration(self, tel, emitter):
        with tel.phase_context(1, "parse"):
            time.sleep(0.05)
        with tel.phase_context(2, "validate"):
            time.sleep(0.05)

        summary = tel.get_session_summary()
        assert summary["total_duration_seconds"] >= 0.1

    def test_session_summary_empty_pipeline(self, tel, emitter):
        summary = tel.get_session_summary()
        assert summary["phases"] == {}
        assert summary["agents"] == {}
        assert summary["total_duration_seconds"] == pytest.approx(0.0)
        assert summary["total_cost_usd"] == pytest.approx(0.0)

    def test_session_summary_phases_dict(self, tel, emitter):
        with tel.phase_context(5, "implement") as m:
            m["features_count"] = 3

        summary = tel.get_session_summary()
        assert 5 in summary["phases"]
        assert summary["phases"][5]["features_count"] == 3

    def test_get_phase_summary_reflects_stored_metrics(self, tel, emitter):
        with tel.phase_context(3, "explore") as m:
            m["files_scanned"] = 42
            m["languages_detected"] = ["python", "yaml"]

        phase = tel.get_phase_summary(3)
        assert phase["files_scanned"] == 42
        assert "python" in phase["languages_detected"]

    def test_get_phase_summary_returns_copy(self, tel, emitter):
        """Mutating the returned dict should not affect internal state."""
        with tel.phase_context(1, "parse") as m:
            m["extra"] = "original"

        summary1 = tel.get_phase_summary(1)
        summary1["extra"] = "mutated"

        summary2 = tel.get_phase_summary(1)
        assert summary2["extra"] == "original"


# ---------------------------------------------------------------------------
# Mock EventEmitter integration
# ---------------------------------------------------------------------------


class TestMockEmitterIntegration:
    def test_mock_emitter_receives_all_events(self):
        mock_emitter = MagicMock(spec=EventEmitter)
        tel = PipelineTelemetry(mock_emitter, session_id="mock-session")

        with tel.phase_context(1, "parse"):
            pass

        tel.record_agent_dispatch("t1", "implement", "feat-1")
        tel.record_agent_result("t1", "success", [], [])
        tel.record_token_usage("t1", 100, 50, "sonnet")

        # emit should have been called: phase.enter, phase.exit,
        # agent.dispatch, agent.result, agent.token_usage  = 5 times
        assert mock_emitter.emit.call_count == 5

    def test_mock_emitter_event_types_in_order(self):
        emitted_types: List[str] = []
        real_emitter = EventEmitter()
        real_emitter.subscribe(lambda e: emitted_types.append(e.event_type))

        tel = PipelineTelemetry(real_emitter, session_id="order-session")

        with tel.phase_context(1, "parse"):
            pass
        tel.record_agent_dispatch("t1", "implement", "f1")
        tel.record_agent_result("t1", "success", [], [])
        tel.record_token_usage("t1", 10, 5, "haiku")

        assert emitted_types == [
            "phase.enter",
            "phase.exit",
            "agent.dispatch",
            "agent.result",
            "agent.token_usage",
        ]
