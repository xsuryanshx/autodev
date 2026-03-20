"""Tests for post-run session analysis."""

import json
import os
import shutil
import tempfile

import pytest

from core.analysis import SessionAnalyzer, MODEL_PRICING


def _write_events(path, events):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def _sample_events(session_id="test123"):
    """A realistic set of events for a 2-agent session."""
    return [
        {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "orchestrator", "phase": 0, "data": {}, "session_id": session_id},
        {"event_type": "phase.enter", "timestamp": "2026-03-20T10:00:01Z", "source": "orchestrator", "phase": 1, "data": {"phase_name": "Parse"}, "session_id": session_id},
        {"event_type": "phase.exit", "timestamp": "2026-03-20T10:00:03Z", "source": "orchestrator", "phase": 1, "data": {"duration_seconds": 2.0}, "session_id": session_id},
        {"event_type": "phase.enter", "timestamp": "2026-03-20T10:00:03Z", "source": "orchestrator", "phase": 5, "data": {"phase_name": "Implement"}, "session_id": session_id},
        {"event_type": "agent.dispatch", "timestamp": "2026-03-20T10:00:04Z", "source": "orchestrator", "phase": 5, "data": {"task_id": "feat-1"}, "session_id": session_id},
        {"event_type": "agent.dispatch", "timestamp": "2026-03-20T10:00:04Z", "source": "orchestrator", "phase": 5, "data": {"task_id": "feat-2"}, "session_id": session_id},
        {"event_type": "file.write", "timestamp": "2026-03-20T10:01:00Z", "source": "coder-1", "phase": 5, "data": {"path": "src/auth.py", "is_new": True}, "session_id": session_id},
        {"event_type": "file.write", "timestamp": "2026-03-20T10:01:30Z", "source": "coder-2", "phase": 5, "data": {"path": "src/rate.py", "is_new": True}, "session_id": session_id},
        {"event_type": "token.usage", "timestamp": "2026-03-20T10:02:00Z", "source": "coder-1", "phase": 5, "data": {"input_tokens": 10000, "output_tokens": 5000, "model": "sonnet"}, "session_id": session_id},
        {"event_type": "token.usage", "timestamp": "2026-03-20T10:02:00Z", "source": "coder-2", "phase": 5, "data": {"input_tokens": 8000, "output_tokens": 4000, "model": "sonnet"}, "session_id": session_id},
        {"event_type": "test.pass", "timestamp": "2026-03-20T10:03:00Z", "source": "coder-1", "phase": 5, "data": {"count": 10}, "session_id": session_id},
        {"event_type": "agent.complete", "timestamp": "2026-03-20T10:03:00Z", "source": "coder-1", "phase": 5, "data": {"task_id": "feat-1", "status": "completed", "files_created": ["src/auth.py"]}, "session_id": session_id},
        {"event_type": "agent.complete", "timestamp": "2026-03-20T10:04:00Z", "source": "coder-2", "phase": 5, "data": {"task_id": "feat-2", "status": "completed", "files_created": ["src/rate.py"]}, "session_id": session_id},
        {"event_type": "phase.exit", "timestamp": "2026-03-20T10:04:00Z", "source": "orchestrator", "phase": 5, "data": {"duration_seconds": 237.0}, "session_id": session_id},
        {"event_type": "session.end", "timestamp": "2026-03-20T10:05:00Z", "source": "orchestrator", "phase": 8, "data": {}, "session_id": session_id},
    ]


class TestGenerateReport:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "events.jsonl")

    def teardown_method(self):
        shutil.rmtree(self.tmp)

    def test_basic_report(self):
        _write_events(self.path, _sample_events())
        analyzer = SessionAnalyzer(self.path)
        report = analyzer.generate_report()

        assert report["session_id"] == "test123"
        assert report["total_duration_seconds"] == 300.0  # 10:00:00 to 10:05:00

    def test_phases_in_report(self):
        _write_events(self.path, _sample_events())
        report = SessionAnalyzer(self.path).generate_report()

        assert len(report["phases"]) == 2
        assert report["phases"][0]["phase"] == 1
        assert report["phases"][0]["name"] == "Parse"
        assert report["phases"][0]["duration_seconds"] == 2.0

    def test_agents_in_report(self):
        _write_events(self.path, _sample_events())
        report = SessionAnalyzer(self.path).generate_report()

        assert len(report["agents"]) == 2
        task_ids = {a["task_id"] for a in report["agents"]}
        assert task_ids == {"feat-1", "feat-2"}

    def test_agent_duration(self):
        _write_events(self.path, _sample_events())
        report = SessionAnalyzer(self.path).generate_report()

        feat1 = [a for a in report["agents"] if a["task_id"] == "feat-1"][0]
        # dispatched at 10:00:04, completed at 10:03:00 = 176s
        assert feat1["duration_seconds"] == 176.0

    def test_token_summary(self):
        _write_events(self.path, _sample_events())
        report = SessionAnalyzer(self.path).generate_report()

        assert report["tokens"]["total_input"] == 18000
        assert report["tokens"]["total_output"] == 9000

    def test_cost_calculation(self):
        _write_events(self.path, _sample_events())
        report = SessionAnalyzer(self.path).generate_report()

        # Sonnet: 18000 input / 1M * $3 = $0.054
        # Sonnet: 9000 output / 1M * $15 = $0.135
        # Total: $0.189
        assert abs(report["tokens"]["estimated_cost_usd"] - 0.189) < 0.001

    def test_files_summary(self):
        _write_events(self.path, _sample_events())
        report = SessionAnalyzer(self.path).generate_report()

        assert report["files_changed"]["total_created"] == 2
        assert report["files_changed"]["total_modified"] == 0

    def test_test_results(self):
        _write_events(self.path, _sample_events())
        report = SessionAnalyzer(self.path).generate_report()

        assert report["test_results"]["passed"] == 10
        assert report["test_results"]["failed"] == 0
        assert report["test_results"]["total"] == 10

    def test_empty_events(self):
        _write_events(self.path, [])
        report = SessionAnalyzer(self.path).generate_report()

        assert report["session_id"] == "unknown"
        assert report["total_duration_seconds"] == 0.0
        assert report["phases"] == []
        assert report["agents"] == []

    def test_missing_events_file(self):
        report = SessionAnalyzer("/nonexistent/path.jsonl").generate_report()
        assert report["session_id"] == "unknown"


class TestIdentifyBottlenecks:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "events.jsonl")

    def teardown_method(self):
        shutil.rmtree(self.tmp)

    def test_slow_agent_detected(self):
        """Agent that takes 3x longer than others should be flagged."""
        events = [
            {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 0, "data": {}, "session_id": "s1"},
            {"event_type": "agent.dispatch", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 5, "data": {"task_id": "fast-1"}, "session_id": "s1"},
            {"event_type": "agent.dispatch", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 5, "data": {"task_id": "fast-2"}, "session_id": "s1"},
            {"event_type": "agent.dispatch", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 5, "data": {"task_id": "slow-1"}, "session_id": "s1"},
            {"event_type": "agent.complete", "timestamp": "2026-03-20T10:01:00Z", "source": "o", "phase": 5, "data": {"task_id": "fast-1"}, "session_id": "s1"},
            {"event_type": "agent.complete", "timestamp": "2026-03-20T10:01:00Z", "source": "o", "phase": 5, "data": {"task_id": "fast-2"}, "session_id": "s1"},
            {"event_type": "agent.complete", "timestamp": "2026-03-20T10:10:00Z", "source": "o", "phase": 5, "data": {"task_id": "slow-1"}, "session_id": "s1"},
        ]
        _write_events(self.path, events)
        bottlenecks = SessionAnalyzer(self.path).identify_bottlenecks()

        slow = [b for b in bottlenecks if b["type"] == "slow_agent"]
        assert len(slow) == 1
        assert "slow-1" in slow[0]["description"]

    def test_many_retries_detected(self):
        events = [
            {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 0, "data": {}, "session_id": "s1"},
            {"event_type": "agent.dispatch", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 5, "data": {"task_id": "flaky"}, "session_id": "s1"},
            {"event_type": "agent.error", "timestamp": "2026-03-20T10:01:00Z", "source": "o", "phase": 5, "data": {"task_id": "flaky", "error": "timeout"}, "session_id": "s1"},
            {"event_type": "agent.error", "timestamp": "2026-03-20T10:02:00Z", "source": "o", "phase": 5, "data": {"task_id": "flaky", "error": "timeout"}, "session_id": "s1"},
            {"event_type": "agent.complete", "timestamp": "2026-03-20T10:03:00Z", "source": "o", "phase": 5, "data": {"task_id": "flaky"}, "session_id": "s1"},
        ]
        _write_events(self.path, events)
        bottlenecks = SessionAnalyzer(self.path).identify_bottlenecks()

        retry = [b for b in bottlenecks if b["type"] == "many_retries"]
        assert len(retry) == 1
        assert "flaky" in retry[0]["description"]

    def test_conflict_detected(self):
        events = [
            {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 0, "data": {}, "session_id": "s1"},
            {"event_type": "merge.conflict", "timestamp": "2026-03-20T10:05:00Z", "source": "o", "phase": 6, "data": {"path": "src/config.py"}, "session_id": "s1"},
        ]
        _write_events(self.path, events)
        bottlenecks = SessionAnalyzer(self.path).identify_bottlenecks()

        conflicts = [b for b in bottlenecks if b["type"] == "conflict"]
        assert len(conflicts) == 1
        assert "src/config.py" in conflicts[0]["description"]

    def test_no_bottlenecks(self):
        """Equal-duration agents should produce no bottlenecks."""
        events = [
            {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 0, "data": {}, "session_id": "s1"},
            {"event_type": "agent.dispatch", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 5, "data": {"task_id": "a"}, "session_id": "s1"},
            {"event_type": "agent.dispatch", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 5, "data": {"task_id": "b"}, "session_id": "s1"},
            {"event_type": "agent.complete", "timestamp": "2026-03-20T10:01:00Z", "source": "o", "phase": 5, "data": {"task_id": "a"}, "session_id": "s1"},
            {"event_type": "agent.complete", "timestamp": "2026-03-20T10:01:00Z", "source": "o", "phase": 5, "data": {"task_id": "b"}, "session_id": "s1"},
        ]
        _write_events(self.path, events)
        bottlenecks = SessionAnalyzer(self.path).identify_bottlenecks()
        assert len(bottlenecks) == 0


class TestCompareRuns:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp)

    def test_compare_durations(self):
        path_a = os.path.join(self.tmp, "a.jsonl")
        path_b = os.path.join(self.tmp, "b.jsonl")

        events_a = [
            {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 0, "data": {}, "session_id": "a"},
            {"event_type": "session.end", "timestamp": "2026-03-20T10:05:00Z", "source": "o", "phase": 8, "data": {}, "session_id": "a"},
        ]
        events_b = [
            {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 0, "data": {}, "session_id": "b"},
            {"event_type": "session.end", "timestamp": "2026-03-20T10:10:00Z", "source": "o", "phase": 8, "data": {}, "session_id": "b"},
        ]
        _write_events(path_a, events_a)
        _write_events(path_b, events_b)

        comp = SessionAnalyzer(path_a).compare_runs(path_b)
        assert comp["duration_delta_seconds"] == -300.0  # 5 min vs 10 min
        assert comp["duration_delta_percent"] == -50.0

    def test_compare_tokens(self):
        path_a = os.path.join(self.tmp, "a.jsonl")
        path_b = os.path.join(self.tmp, "b.jsonl")

        events_a = [
            {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 0, "data": {}, "session_id": "a"},
            {"event_type": "token.usage", "timestamp": "2026-03-20T10:01:00Z", "source": "o", "phase": 5, "data": {"input_tokens": 10000, "output_tokens": 5000, "model": "sonnet"}, "session_id": "a"},
            {"event_type": "session.end", "timestamp": "2026-03-20T10:05:00Z", "source": "o", "phase": 8, "data": {}, "session_id": "a"},
        ]
        events_b = [
            {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 0, "data": {}, "session_id": "b"},
            {"event_type": "token.usage", "timestamp": "2026-03-20T10:01:00Z", "source": "o", "phase": 5, "data": {"input_tokens": 20000, "output_tokens": 10000, "model": "sonnet"}, "session_id": "b"},
            {"event_type": "session.end", "timestamp": "2026-03-20T10:10:00Z", "source": "o", "phase": 8, "data": {}, "session_id": "b"},
        ]
        _write_events(path_a, events_a)
        _write_events(path_b, events_b)

        comp = SessionAnalyzer(path_a).compare_runs(path_b)
        assert comp["token_delta"] == -15000  # 15k vs 30k


class TestSaveReport:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp)

    def test_save_creates_json(self):
        events_path = os.path.join(self.tmp, "events.jsonl")
        _write_events(events_path, _sample_events())

        report_path = os.path.join(self.tmp, "report.json")
        SessionAnalyzer(events_path).save_report(report_path)

        assert os.path.exists(report_path)
        with open(report_path) as f:
            data = json.load(f)
        assert "session_id" in data
        assert "phases" in data


class TestRenderHtmlReport:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp)

    def test_render_produces_html(self):
        events_path = os.path.join(self.tmp, "events.jsonl")
        _write_events(events_path, _sample_events())

        template_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "dashboard",
            "templates",
            "report.html",
        )
        output_path = os.path.join(self.tmp, "out.html")

        html = SessionAnalyzer(events_path).render_html_report(template_path, output_path)
        assert "test123" in html
        assert "AutoDev Session Report" in html
        assert os.path.exists(output_path)

    def test_render_substitutes_values(self):
        events_path = os.path.join(self.tmp, "events.jsonl")
        _write_events(events_path, _sample_events())

        template_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "dashboard",
            "templates",
            "report.html",
        )
        output_path = os.path.join(self.tmp, "out.html")

        html = SessionAnalyzer(events_path).render_html_report(template_path, output_path)
        # Should contain the session id, not the placeholder
        assert "$session_id" not in html
        assert "test123" in html


class TestCostCalculation:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp)

    def test_sonnet_pricing(self):
        events = [
            {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 0, "data": {}, "session_id": "s"},
            {"event_type": "token.usage", "timestamp": "2026-03-20T10:01:00Z", "source": "o", "phase": 5, "data": {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "model": "sonnet"}, "session_id": "s"},
        ]
        _write_events(os.path.join(self.tmp, "e.jsonl"), events)
        report = SessionAnalyzer(os.path.join(self.tmp, "e.jsonl")).generate_report()
        # 1M input * $3/1M + 1M output * $15/1M = $18
        assert report["tokens"]["estimated_cost_usd"] == 18.0

    def test_opus_pricing(self):
        events = [
            {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 0, "data": {}, "session_id": "s"},
            {"event_type": "token.usage", "timestamp": "2026-03-20T10:01:00Z", "source": "o", "phase": 5, "data": {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "model": "opus"}, "session_id": "s"},
        ]
        _write_events(os.path.join(self.tmp, "e.jsonl"), events)
        report = SessionAnalyzer(os.path.join(self.tmp, "e.jsonl")).generate_report()
        # 1M input * $15/1M + 1M output * $75/1M = $90
        assert report["tokens"]["estimated_cost_usd"] == 90.0

    def test_haiku_pricing(self):
        events = [
            {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 0, "data": {}, "session_id": "s"},
            {"event_type": "token.usage", "timestamp": "2026-03-20T10:01:00Z", "source": "o", "phase": 5, "data": {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "model": "haiku"}, "session_id": "s"},
        ]
        _write_events(os.path.join(self.tmp, "e.jsonl"), events)
        report = SessionAnalyzer(os.path.join(self.tmp, "e.jsonl")).generate_report()
        # 1M input * $0.25/1M + 1M output * $1.25/1M = $1.50
        assert report["tokens"]["estimated_cost_usd"] == 1.5

    def test_mixed_models(self):
        events = [
            {"event_type": "session.start", "timestamp": "2026-03-20T10:00:00Z", "source": "o", "phase": 0, "data": {}, "session_id": "s"},
            {"event_type": "token.usage", "timestamp": "2026-03-20T10:01:00Z", "source": "o", "phase": 5, "data": {"input_tokens": 10000, "output_tokens": 5000, "model": "sonnet"}, "session_id": "s"},
            {"event_type": "token.usage", "timestamp": "2026-03-20T10:01:00Z", "source": "o", "phase": 7, "data": {"input_tokens": 8000, "output_tokens": 3000, "model": "opus"}, "session_id": "s"},
        ]
        _write_events(os.path.join(self.tmp, "e.jsonl"), events)
        report = SessionAnalyzer(os.path.join(self.tmp, "e.jsonl")).generate_report()

        by_model = report["tokens"]["by_model"]
        assert "sonnet" in by_model
        assert "opus" in by_model
        assert by_model["sonnet"]["input"] == 10000
        assert by_model["opus"]["input"] == 8000
