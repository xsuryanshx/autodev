"""
Structured event system for AutoDev observability.

Provides AgentEvent dataclass and EventEmitter for publishing, subscribing,
and persisting events to a JSONL file.
"""

from __future__ import annotations

import datetime
import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Valid event type constants
# ---------------------------------------------------------------------------

EVENT_TYPES = frozenset(
    [
        # Session lifecycle
        "session.start",
        "session.end",
        # Phase lifecycle
        "phase.enter",
        "phase.exit",
        # Agent lifecycle
        "agent.dispatch",
        "agent.start",
        "agent.progress",
        "agent.complete",
        "agent.error",
        # File operations
        "file.read",
        "file.write",
        "file.delete",
        # Test operations
        "test.run",
        "test.pass",
        "test.fail",
        # Merge operations
        "merge.start",
        "merge.conflict",
        "merge.resolve",
        # Review
        "review.verdict",
    ]
)


# ---------------------------------------------------------------------------
# AgentEvent dataclass
# ---------------------------------------------------------------------------


def _default_session_id() -> str:
    return uuid.uuid4().hex[:8]


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def make_timestamp() -> str:
    """Public helper to generate a UTC ISO-8601 timestamp."""
    return _utcnow()


@dataclass
class AgentEvent:
    """Structured event representing an observable action within AutoDev.

    Attributes:
        event_type: One of the defined EVENT_TYPES strings.
        source: Identifier for the emitting component, e.g. "orchestrator",
            "coder-feat-1", "researcher-feat-2".
        phase: Pipeline phase (1-8) in which the event occurred.
        data: Arbitrary JSON-serialisable payload specific to the event type.
        session_id: Short identifier shared across all events in one run.
        timestamp: ISO-8601 UTC timestamp set automatically when not provided.
    """

    event_type: str
    source: str
    phase: int
    data: Dict
    session_id: str = field(default_factory=_default_session_id)
    timestamp: str = field(default_factory=_utcnow)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict:
        """Return a plain dict suitable for JSON serialisation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "AgentEvent":
        """Reconstruct an AgentEvent from a plain dict."""
        return cls(
            event_type=d["event_type"],
            source=d["source"],
            phase=d["phase"],
            data=d["data"],
            session_id=d["session_id"],
            timestamp=d["timestamp"],
        )

    def to_json(self) -> str:
        """Serialise to a JSON string (single line, no trailing newline)."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, s: str) -> "AgentEvent":
        """Deserialise from a JSON string."""
        return cls.from_dict(json.loads(s))


# ---------------------------------------------------------------------------
# EventEmitter
# ---------------------------------------------------------------------------


class EventEmitter:
    """Thread-safe event emitter with JSONL persistence.

    Usage::

        emitter = EventEmitter(output_path=".autodev/events.jsonl")
        emitter.subscribe(lambda e: print(e.event_type))
        emitter.subscribe_filtered("phase.enter", on_phase_enter)

        event = AgentEvent(
            event_type="phase.enter",
            source="orchestrator",
            phase=3,
            data={"phase_name": "Explore"},
        )
        emitter.emit(event)
    """

    DEFAULT_OUTPUT_PATH = os.path.join(".autodev", "events.jsonl")

    def __init__(self, output_path: Optional[str] = None) -> None:
        self._output_path: str = output_path or self.DEFAULT_OUTPUT_PATH
        self._lock = threading.Lock()
        # List of (event_type_filter | None, callback)
        self._subscribers: List[tuple] = []

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable[[AgentEvent], None]) -> None:
        """Register *callback* to receive every event."""
        with self._lock:
            self._subscribers.append((None, callback))

    def subscribe_filtered(
        self,
        event_type: str,
        callback: Callable[[AgentEvent], None],
    ) -> None:
        """Register *callback* to receive events matching *event_type* only."""
        with self._lock:
            self._subscribers.append((event_type, callback))

    def unsubscribe_all(self) -> None:
        """Remove all registered subscribers (useful in tests)."""
        with self._lock:
            self._subscribers.clear()

    # ------------------------------------------------------------------
    # Emitting
    # ------------------------------------------------------------------

    def emit(self, event: AgentEvent) -> None:
        """Publish *event* to all matching subscribers and persist to JSONL.

        Thread-safe: multiple threads may call emit() concurrently.
        """
        with self._lock:
            # Persist first so the log is consistent even if a callback raises.
            self._persist(event)
            # Snapshot the subscriber list while holding the lock.
            subscribers_snapshot = list(self._subscribers)

        # Invoke callbacks outside the lock to avoid deadlocks.
        for event_type_filter, callback in subscribers_snapshot:
            if event_type_filter is None or event_type_filter == event.event_type:
                try:
                    callback(event)
                except Exception:
                    # Callbacks must not break the emitter.
                    pass

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, event: AgentEvent) -> None:
        """Append *event* as a JSON line to the output file.

        Creates parent directories as needed.
        Must be called while holding self._lock.
        """
        parent = os.path.dirname(self._output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self._output_path, "a", encoding="utf-8") as fh:
            fh.write(event.to_json() + "\n")


# ---------------------------------------------------------------------------
# Loading events from JSONL
# ---------------------------------------------------------------------------


def load_events(path: str) -> List[AgentEvent]:
    """Load and return all events from a JSONL file at *path*.

    Skips blank lines and lines that cannot be parsed.

    Args:
        path: Filesystem path to a JSONL events file.

    Returns:
        List of AgentEvent instances in file order.
    """
    events: List[AgentEvent] = []
    if not os.path.exists(path):
        return events
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(AgentEvent.from_json(line))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    return events
