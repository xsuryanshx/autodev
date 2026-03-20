"""
core/telemetry.py — Pipeline telemetry collector for AutoDev.

Tracks phase durations, agent dispatches/results, and token usage.
Provides cost estimation based on model pricing.

Usage::

    emitter = EventEmitter()
    tel = PipelineTelemetry(emitter, session_id="run-abc123")

    with tel.phase_context(1, "parse"):
        # ... phase 1 work ...

    tel.record_agent_dispatch("task-1", "implement", "feat-1")
    tel.record_agent_result("task-1", "success", ["new.py"], ["old.py"])
    tel.record_token_usage("task-1", 1000, 500, "sonnet")

    summary = tel.get_session_summary()
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Generator, List, Optional

from core.events import AgentEvent, EventEmitter, make_timestamp


# ---------------------------------------------------------------------------
# Model pricing (per 1 000 000 tokens)
# ---------------------------------------------------------------------------

_MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "sonnet": {"input": 3.0, "output": 15.0},
    "haiku": {"input": 0.25, "output": 1.25},
    "opus": {"input": 15.0, "output": 75.0},
}

_PER_MILLION = 1_000_000


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated cost in USD for the given token counts and model."""
    pricing = _MODEL_PRICING.get(model.lower(), {"input": 0.0, "output": 0.0})
    return (
        input_tokens * pricing["input"] / _PER_MILLION
        + output_tokens * pricing["output"] / _PER_MILLION
    )


# ---------------------------------------------------------------------------
# PipelineTelemetry
# ---------------------------------------------------------------------------


class PipelineTelemetry:
    """Collect and expose metrics for a single AutoDev pipeline run."""

    def __init__(self, emitter: EventEmitter, session_id: str) -> None:
        self._emitter = emitter
        self._session_id = session_id

        # Keyed by phase_num (int)
        self._phases: Dict[int, dict] = {}

        # Keyed by task_id (str)
        self._agents: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Phase tracking
    # ------------------------------------------------------------------

    @contextmanager
    def phase_context(
        self, phase_num: int, phase_name: str
    ) -> Generator[dict, None, None]:
        """Context manager that times a phase and emits enter/exit events.

        Yields a *metrics* dict that callers may populate with phase-specific
        data (e.g. ``metrics["files_scanned"] = 42``).  The dict is stored
        under ``self._phases[phase_num]`` after the block exits.
        """
        metrics: dict = {"phase_num": phase_num, "phase_name": phase_name}
        self._phases[phase_num] = metrics

        enter_event = AgentEvent(
            event_type="phase.enter",
            timestamp=make_timestamp(),
            source="telemetry",
            phase=phase_num,
            data={"phase_name": phase_name},
            session_id=self._session_id,
        )
        self._emitter.emit(enter_event)

        start = time.monotonic()
        try:
            yield metrics
        finally:
            duration = time.monotonic() - start
            metrics["duration_seconds"] = duration

            exit_event = AgentEvent(
                event_type="phase.exit",
                timestamp=make_timestamp(),
                source="telemetry",
                phase=phase_num,
                data={"phase_name": phase_name, "duration_seconds": duration},
                session_id=self._session_id,
            )
            self._emitter.emit(exit_event)

    # ------------------------------------------------------------------
    # Agent tracking
    # ------------------------------------------------------------------

    def record_agent_dispatch(
        self, task_id: str, skill: str, feature_id: str
    ) -> None:
        """Record when an agent is dispatched for a task."""
        self._agents[task_id] = {
            "task_id": task_id,
            "skill": skill,
            "feature_id": feature_id,
            "dispatched_at": make_timestamp(),
            "dispatch_monotonic": time.monotonic(),
            "status": "dispatched",
            "files_created": [],
            "files_modified": [],
            "commits": 0,
            "retries": 0,
        }

        self._emitter.emit(
            AgentEvent(
                event_type="agent.dispatch",
                timestamp=self._agents[task_id]["dispatched_at"],
                source="telemetry",
                phase=0,
                data={"task_id": task_id, "skill": skill, "feature_id": feature_id},
                session_id=self._session_id,
            )
        )

    def record_agent_result(
        self,
        task_id: str,
        status: str,
        files_created: List[str],
        files_modified: List[str],
    ) -> None:
        """Record the outcome of an agent task."""
        record = self._agents.setdefault(
            task_id,
            {
                "task_id": task_id,
                "dispatch_monotonic": time.monotonic(),
                "commits": 0,
                "retries": 0,
            },
        )
        record["status"] = status
        record["files_created"] = list(files_created)
        record["files_modified"] = list(files_modified)
        record["completed_at"] = make_timestamp()

        dispatch_mono = record.get("dispatch_monotonic", time.monotonic())
        record["duration_seconds"] = time.monotonic() - dispatch_mono

        self._emitter.emit(
            AgentEvent(
                event_type="agent.result",
                timestamp=record["completed_at"],
                source="telemetry",
                phase=0,
                data={
                    "task_id": task_id,
                    "status": status,
                    "files_created": files_created,
                    "files_modified": files_modified,
                },
                session_id=self._session_id,
            )
        )

    # ------------------------------------------------------------------
    # Token / cost tracking
    # ------------------------------------------------------------------

    def record_token_usage(
        self,
        task_id: str,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ) -> None:
        """Record token usage for a task and compute estimated cost."""
        record = self._agents.setdefault(
            task_id,
            {
                "task_id": task_id,
                "dispatch_monotonic": time.monotonic(),
                "commits": 0,
                "retries": 0,
            },
        )
        record["input_tokens"] = input_tokens
        record["output_tokens"] = output_tokens
        record["model"] = model
        record["cost_usd"] = _cost_usd(model, input_tokens, output_tokens)

        self._emitter.emit(
            AgentEvent(
                event_type="agent.token_usage",
                timestamp=make_timestamp(),
                source="telemetry",
                phase=0,
                data={
                    "task_id": task_id,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "model": model,
                    "cost_usd": record["cost_usd"],
                },
                session_id=self._session_id,
            )
        )

    # ------------------------------------------------------------------
    # Summary helpers
    # ------------------------------------------------------------------

    def get_phase_summary(self, phase_num: int) -> dict:
        """Return metrics for a specific phase.

        Returns an empty dict if the phase has not been recorded.
        """
        return dict(self._phases.get(phase_num, {}))

    def get_session_summary(self) -> dict:
        """Return complete session metrics aggregated across all phases."""
        total_duration = sum(
            p.get("duration_seconds", 0.0) for p in self._phases.values()
        )

        total_input_tokens = sum(
            a.get("input_tokens", 0) for a in self._agents.values()
        )
        total_output_tokens = sum(
            a.get("output_tokens", 0) for a in self._agents.values()
        )
        total_cost = sum(
            a.get("cost_usd", 0.0) for a in self._agents.values()
        )

        total_files_created: List[str] = []
        total_files_modified: List[str] = []
        for agent in self._agents.values():
            total_files_created.extend(agent.get("files_created", []))
            total_files_modified.extend(agent.get("files_modified", []))

        return {
            "session_id": self._session_id,
            "phases": {k: dict(v) for k, v in self._phases.items()},
            "agents": {k: dict(v) for k, v in self._agents.items()},
            "total_duration_seconds": total_duration,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cost_usd": total_cost,
            "total_files_created": total_files_created,
            "total_files_modified": total_files_modified,
        }
