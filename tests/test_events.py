"""Comprehensive tests for core/events.py."""

import json
import os
import shutil
import tempfile
import threading
import time
from typing import List

import pytest

from core.events import AgentEvent, EventEmitter, EVENT_TYPES, load_events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_dir():
    """Yield a temporary directory and remove it after the test."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def jsonl_path(temp_dir):
    """Return a path inside temp_dir for a JSONL events file."""
    return os.path.join(temp_dir, "events.jsonl")


@pytest.fixture
def emitter(jsonl_path):
    """Return an EventEmitter writing to a temp JSONL file."""
    return EventEmitter(output_path=jsonl_path)


@pytest.fixture
def sample_event():
    """Return a minimal valid AgentEvent."""
    return AgentEvent(
        event_type="phase.enter",
        source="orchestrator",
        phase=3,
        data={"phase_name": "Explore"},
        session_id="abc12345",
        timestamp="2026-01-01T00:00:00",
    )


# ---------------------------------------------------------------------------
# TestAgentEvent — dataclass creation and serialisation
# ---------------------------------------------------------------------------


class TestAgentEvent:
    def test_creation_with_explicit_fields(self):
        event = AgentEvent(
            event_type="session.start",
            source="orchestrator",
            phase=1,
            data={"issue_url": "https://github.com/x/y/issues/1"},
            session_id="test0001",
            timestamp="2026-01-01T00:00:00",
        )
        assert event.event_type == "session.start"
        assert event.source == "orchestrator"
        assert event.phase == 1
        assert event.data == {"issue_url": "https://github.com/x/y/issues/1"}
        assert event.session_id == "test0001"
        assert event.timestamp == "2026-01-01T00:00:00"

    def test_default_session_id_is_8_hex_chars(self):
        event = AgentEvent(
            event_type="session.start",
            source="orchestrator",
            phase=1,
            data={},
        )
        assert len(event.session_id) == 8
        # Validate hex-only characters
        int(event.session_id, 16)

    def test_default_timestamp_is_iso_format(self):
        event = AgentEvent(
            event_type="session.start",
            source="orchestrator",
            phase=1,
            data={},
        )
        # Should be parseable as ISO datetime
        from datetime import datetime
        datetime.fromisoformat(event.timestamp)

    def test_two_events_get_different_default_session_ids(self):
        e1 = AgentEvent(event_type="session.start", source="o", phase=1, data={})
        e2 = AgentEvent(event_type="session.end", source="o", phase=1, data={})
        # UUIDs are extremely unlikely to collide
        assert e1.session_id != e2.session_id

    def test_to_dict_returns_all_fields(self, sample_event):
        d = sample_event.to_dict()
        assert d["event_type"] == "phase.enter"
        assert d["source"] == "orchestrator"
        assert d["phase"] == 3
        assert d["data"] == {"phase_name": "Explore"}
        assert d["session_id"] == "abc12345"
        assert d["timestamp"] == "2026-01-01T00:00:00"

    def test_from_dict_roundtrip(self, sample_event):
        d = sample_event.to_dict()
        restored = AgentEvent.from_dict(d)
        assert restored.event_type == sample_event.event_type
        assert restored.source == sample_event.source
        assert restored.phase == sample_event.phase
        assert restored.data == sample_event.data
        assert restored.session_id == sample_event.session_id
        assert restored.timestamp == sample_event.timestamp

    def test_to_json_is_valid_json(self, sample_event):
        s = sample_event.to_json()
        parsed = json.loads(s)
        assert parsed["event_type"] == "phase.enter"

    def test_from_json_roundtrip(self, sample_event):
        restored = AgentEvent.from_json(sample_event.to_json())
        assert restored.event_type == sample_event.event_type
        assert restored.data == sample_event.data

    def test_data_field_supports_nested_structures(self):
        event = AgentEvent(
            event_type="agent.complete",
            source="coder-feat-1",
            phase=5,
            data={
                "feature_id": "feat-1",
                "files_modified": ["core/events.py"],
                "test_results": {"passed": 10, "failed": 0},
            },
        )
        d = event.to_dict()
        assert d["data"]["test_results"]["passed"] == 10

    def test_to_json_produces_single_line(self, sample_event):
        s = sample_event.to_json()
        assert "\n" not in s


# ---------------------------------------------------------------------------
# TestEventEmitter — emit and subscribe
# ---------------------------------------------------------------------------


class TestEventEmitter:
    def test_subscribe_callback_receives_event(self, emitter, sample_event):
        received: List[AgentEvent] = []
        emitter.subscribe(received.append)
        emitter.emit(sample_event)
        assert len(received) == 1
        assert received[0].event_type == "phase.enter"

    def test_multiple_subscribers_all_receive_event(self, emitter, sample_event):
        bucket_a: List[AgentEvent] = []
        bucket_b: List[AgentEvent] = []
        emitter.subscribe(bucket_a.append)
        emitter.subscribe(bucket_b.append)
        emitter.emit(sample_event)
        assert len(bucket_a) == 1
        assert len(bucket_b) == 1

    def test_subscribe_receives_all_event_types(self, emitter):
        received: List[str] = []
        emitter.subscribe(lambda e: received.append(e.event_type))

        for et in ["session.start", "phase.enter", "agent.complete"]:
            emitter.emit(
                AgentEvent(event_type=et, source="test", phase=1, data={},
                           session_id="s", timestamp="2026-01-01T00:00:00")
            )
        assert received == ["session.start", "phase.enter", "agent.complete"]

    def test_emit_without_subscribers_does_not_raise(self, emitter, sample_event):
        # Should succeed silently
        emitter.emit(sample_event)

    def test_callback_exception_does_not_stop_other_callbacks(self, emitter, sample_event):
        """A misbehaving subscriber must not prevent other subscribers from running."""
        received: List[AgentEvent] = []

        def bad_callback(e):
            raise RuntimeError("boom")

        emitter.subscribe(bad_callback)
        emitter.subscribe(received.append)
        emitter.emit(sample_event)
        assert len(received) == 1

    def test_unsubscribe_all_clears_subscribers(self, emitter, sample_event):
        received: List[AgentEvent] = []
        emitter.subscribe(received.append)
        emitter.unsubscribe_all()
        emitter.emit(sample_event)
        assert received == []


# ---------------------------------------------------------------------------
# TestFilteredSubscriptions
# ---------------------------------------------------------------------------


class TestFilteredSubscriptions:
    def test_filtered_callback_receives_matching_type(self, emitter):
        received: List[AgentEvent] = []
        emitter.subscribe_filtered("phase.enter", received.append)

        emitter.emit(AgentEvent(event_type="phase.enter", source="o", phase=1, data={},
                                session_id="s", timestamp="2026-01-01T00:00:00"))
        assert len(received) == 1

    def test_filtered_callback_does_not_receive_other_types(self, emitter):
        received: List[AgentEvent] = []
        emitter.subscribe_filtered("phase.enter", received.append)

        emitter.emit(AgentEvent(event_type="agent.start", source="o", phase=1, data={},
                                session_id="s", timestamp="2026-01-01T00:00:00"))
        assert received == []

    def test_multiple_filtered_subscriptions_independent(self, emitter):
        phase_events: List[AgentEvent] = []
        agent_events: List[AgentEvent] = []
        emitter.subscribe_filtered("phase.enter", phase_events.append)
        emitter.subscribe_filtered("agent.complete", agent_events.append)

        emitter.emit(AgentEvent(event_type="phase.enter", source="o", phase=1, data={},
                                session_id="s", timestamp="t"))
        emitter.emit(AgentEvent(event_type="agent.complete", source="o", phase=5, data={},
                                session_id="s", timestamp="t"))
        emitter.emit(AgentEvent(event_type="phase.exit", source="o", phase=1, data={},
                                session_id="s", timestamp="t"))

        assert len(phase_events) == 1
        assert len(agent_events) == 1

    def test_filtered_and_unfiltered_subscribers_coexist(self, emitter):
        all_events: List[AgentEvent] = []
        phase_only: List[AgentEvent] = []
        emitter.subscribe(all_events.append)
        emitter.subscribe_filtered("phase.enter", phase_only.append)

        for et in ["phase.enter", "agent.start", "phase.enter"]:
            emitter.emit(AgentEvent(event_type=et, source="o", phase=1, data={},
                                    session_id="s", timestamp="t"))

        assert len(all_events) == 3
        assert len(phase_only) == 2


# ---------------------------------------------------------------------------
# TestJSONLPersistence
# ---------------------------------------------------------------------------


class TestJSONLPersistence:
    def test_emit_creates_jsonl_file(self, emitter, jsonl_path, sample_event):
        emitter.emit(sample_event)
        assert os.path.exists(jsonl_path)

    def test_emitted_events_are_valid_json_lines(self, emitter, jsonl_path, sample_event):
        emitter.emit(sample_event)
        with open(jsonl_path) as fh:
            lines = [l.strip() for l in fh if l.strip()]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["event_type"] == "phase.enter"

    def test_multiple_emits_append_to_file(self, emitter, jsonl_path):
        for i in range(3):
            emitter.emit(
                AgentEvent(event_type="agent.start", source="coder", phase=5,
                           data={"i": i}, session_id="s", timestamp="t")
            )
        with open(jsonl_path) as fh:
            lines = [l for l in fh if l.strip()]
        assert len(lines) == 3

    def test_load_events_returns_correct_count(self, emitter, jsonl_path):
        for i in range(5):
            emitter.emit(
                AgentEvent(event_type="file.write", source="coder", phase=5,
                           data={"path": f"file_{i}.py"}, session_id="s", timestamp="t")
            )
        events = load_events(jsonl_path)
        assert len(events) == 5

    def test_load_events_preserves_field_values(self, emitter, jsonl_path, sample_event):
        emitter.emit(sample_event)
        events = load_events(jsonl_path)
        assert len(events) == 1
        e = events[0]
        assert e.event_type == sample_event.event_type
        assert e.source == sample_event.source
        assert e.phase == sample_event.phase
        assert e.data == sample_event.data
        assert e.session_id == sample_event.session_id
        assert e.timestamp == sample_event.timestamp

    def test_load_events_missing_file_returns_empty_list(self, temp_dir):
        nonexistent = os.path.join(temp_dir, "no_such_file.jsonl")
        events = load_events(nonexistent)
        assert events == []

    def test_load_events_skips_blank_lines(self, temp_dir):
        path = os.path.join(temp_dir, "with_blanks.jsonl")
        event = AgentEvent(event_type="session.start", source="o", phase=1,
                           data={}, session_id="s", timestamp="t")
        with open(path, "w") as fh:
            fh.write("\n")
            fh.write(event.to_json() + "\n")
            fh.write("\n")
        events = load_events(path)
        assert len(events) == 1

    def test_load_events_skips_malformed_lines(self, temp_dir):
        path = os.path.join(temp_dir, "malformed.jsonl")
        event = AgentEvent(event_type="session.end", source="o", phase=1,
                           data={}, session_id="s", timestamp="t")
        with open(path, "w") as fh:
            fh.write("not valid json\n")
            fh.write(event.to_json() + "\n")
        events = load_events(path)
        assert len(events) == 1

    def test_persist_creates_parent_directories(self, temp_dir):
        deep_path = os.path.join(temp_dir, "a", "b", "c", "events.jsonl")
        e = EventEmitter(output_path=deep_path)
        e.emit(AgentEvent(event_type="session.start", source="o", phase=1,
                          data={}, session_id="s", timestamp="t"))
        assert os.path.exists(deep_path)


# ---------------------------------------------------------------------------
# TestThreadSafety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_emits_all_persisted(self, emitter, jsonl_path):
        """N threads each emit M events; total should be N*M in JSONL."""
        n_threads = 8
        events_per_thread = 25

        def worker():
            for _ in range(events_per_thread):
                emitter.emit(
                    AgentEvent(event_type="agent.progress", source="coder",
                               phase=5, data={"msg": "tick"}, session_id="s",
                               timestamp="t")
                )

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        events = load_events(jsonl_path)
        assert len(events) == n_threads * events_per_thread

    def test_concurrent_subscribes_and_emits(self, emitter):
        """Subscribers can be added while events are being emitted."""
        received: List[AgentEvent] = []
        lock = threading.Lock()

        def slow_subscriber(e):
            time.sleep(0.001)
            with lock:
                received.append(e)

        def emit_worker():
            for _ in range(10):
                emitter.emit(
                    AgentEvent(event_type="file.write", source="coder", phase=5,
                               data={}, session_id="s", timestamp="t")
                )

        def subscribe_worker():
            emitter.subscribe(slow_subscriber)

        t_sub = threading.Thread(target=subscribe_worker)
        t_emit = threading.Thread(target=emit_worker)
        t_sub.start()
        t_emit.start()
        t_sub.join()
        t_emit.join()
        # At least some events should have been received (exact count depends on timing)
        # The important thing is that no exception was raised.


# ---------------------------------------------------------------------------
# TestAllEventTypes
# ---------------------------------------------------------------------------


class TestAllEventTypes:
    """Verify that every documented event type can be emitted without error."""

    @pytest.mark.parametrize("event_type", sorted(EVENT_TYPES))
    def test_event_type_can_be_emitted(self, event_type, emitter):
        event = AgentEvent(
            event_type=event_type,
            source="test",
            phase=1,
            data={},
            session_id="s",
            timestamp="t",
        )
        # Should not raise
        emitter.emit(event)

    def test_event_types_constant_has_expected_members(self):
        expected = {
            "session.start", "session.end",
            "phase.enter", "phase.exit",
            "agent.dispatch", "agent.start", "agent.progress",
            "agent.complete", "agent.error",
            "file.read", "file.write", "file.delete",
            "test.run", "test.pass", "test.fail",
            "merge.start", "merge.conflict", "merge.resolve",
            "review.verdict",
        }
        assert expected.issubset(EVENT_TYPES)

    def test_event_types_count(self):
        assert len(EVENT_TYPES) >= 19


# ---------------------------------------------------------------------------
# TestPhaseDurationPattern
# ---------------------------------------------------------------------------


class TestPhaseDurationPattern:
    """Phase.exit events should carry a duration in their data payload."""

    def test_phase_exit_with_duration(self, emitter, jsonl_path):
        emitter.emit(AgentEvent(
            event_type="phase.enter",
            source="orchestrator",
            phase=3,
            data={"phase_name": "Explore"},
            session_id="run001",
            timestamp="2026-01-01T00:00:00",
        ))
        emitter.emit(AgentEvent(
            event_type="phase.exit",
            source="orchestrator",
            phase=3,
            data={"phase_name": "Explore", "duration_seconds": 12.4},
            session_id="run001",
            timestamp="2026-01-01T00:00:12",
        ))
        events = load_events(jsonl_path)
        exit_events = [e for e in events if e.event_type == "phase.exit"]
        assert len(exit_events) == 1
        assert exit_events[0].data["duration_seconds"] == 12.4
