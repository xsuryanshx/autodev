"""Post-run session analysis — report generation and bottleneck identification."""

from __future__ import annotations

import json
import os
from datetime import datetime
from string import Template
from typing import Optional

MODEL_PRICING = {
    "sonnet": {"input_per_1m": 3.0, "output_per_1m": 15.0},
    "haiku": {"input_per_1m": 0.25, "output_per_1m": 1.25},
    "opus": {"input_per_1m": 15.0, "output_per_1m": 75.0},
}

PHASE_NAMES = {
    1: "Parse",
    2: "Validate",
    3: "Explore",
    4: "Plan",
    5: "Implement",
    6: "Merge",
    7: "Review",
    8: "Report",
}


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp, handling the trailing Z."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class SessionAnalyzer:
    """Analyse a completed AutoDev session from its events.jsonl file."""

    def __init__(self, events_path: str = ".autodev/events.jsonl") -> None:
        self.events_path = events_path
        self.events = self._load_events()

    # ── Loading ───────────────────────────────────────────

    def _load_events(self) -> list[dict]:
        events: list[dict] = []
        if not os.path.exists(self.events_path):
            return events
        with open(self.events_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return events

    # ── Public API ────────────────────────────────────────

    def generate_report(self) -> dict:
        session_id = self.events[0]["session_id"] if self.events else "unknown"
        return {
            "session_id": session_id,
            "total_duration_seconds": self._total_duration(),
            "phases": self._phase_summaries(),
            "agents": self._agent_summaries(),
            "tokens": self._token_summary(),
            "files_changed": self._files_summary(),
            "test_results": self._test_summary(),
            "bottlenecks": self.identify_bottlenecks(),
            "recommendations": self._recommendations(),
        }

    def identify_bottlenecks(self) -> list[dict]:
        bottlenecks: list[dict] = []
        self._check_slow_agents(bottlenecks)
        self._check_slow_phases(bottlenecks)
        self._check_retries(bottlenecks)
        self._check_conflicts(bottlenecks)
        return bottlenecks

    def compare_runs(self, other_events_path: str) -> dict:
        other = SessionAnalyzer(other_events_path)
        my = self.generate_report()
        theirs = other.generate_report()

        my_dur = my["total_duration_seconds"]
        other_dur = theirs["total_duration_seconds"]
        dur_delta = my_dur - other_dur
        dur_pct = (dur_delta / other_dur * 100) if other_dur else 0.0

        my_tok = my["tokens"]["total_input"] + my["tokens"]["total_output"]
        other_tok = theirs["tokens"]["total_input"] + theirs["tokens"]["total_output"]

        return {
            "duration_delta_seconds": round(dur_delta, 2),
            "duration_delta_percent": round(dur_pct, 2),
            "token_delta": my_tok - other_tok,
            "cost_delta_usd": round(
                my["tokens"]["estimated_cost_usd"]
                - theirs["tokens"]["estimated_cost_usd"],
                4,
            ),
            "phase_comparison": self._compare_phases(my["phases"], theirs["phases"]),
        }

    def save_report(self, output_path: str = ".autodev/session-report.json") -> None:
        report = self.generate_report()
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

    def render_html_report(self, template_path: str, output_path: str) -> str:
        report = self.generate_report()

        with open(template_path) as f:
            tmpl_str = f.read()

        phase_rows = "".join(
            "<tr><td>{p}</td><td>{n}</td><td>{d:.1f}s</td><td>{s}</td></tr>\n".format(
                p=p["phase"], n=p["name"], d=p["duration_seconds"], s=p["status"]
            )
            for p in report["phases"]
        )

        agent_rows = "".join(
            "<tr><td>{t}</td><td>{d:.1f}s</td><td>{s}</td><td>{r}</td></tr>\n".format(
                t=a["task_id"],
                d=a.get("duration_seconds", 0),
                s=a["status"],
                r=a.get("retries", 0),
            )
            for a in report["agents"]
        )

        bottleneck_items = "".join(
            "<li class='{sev}'>[{SEV}] {desc} — {sug}</li>\n".format(
                sev=b["severity"],
                SEV=b["severity"].upper(),
                desc=b["description"],
                sug=b["suggestion"],
            )
            for b in report["bottlenecks"]
        )
        if not bottleneck_items:
            bottleneck_items = "<li>No bottlenecks detected</li>"

        subs = {
            "session_id": report["session_id"],
            "total_duration": f"{report['total_duration_seconds']:.1f}",
            "total_input_tokens": str(report["tokens"]["total_input"]),
            "total_output_tokens": str(report["tokens"]["total_output"]),
            "estimated_cost": f"{report['tokens']['estimated_cost_usd']:.4f}",
            "files_created": str(report["files_changed"]["total_created"]),
            "files_modified": str(report["files_changed"]["total_modified"]),
            "tests_passed": str(report["test_results"]["passed"]),
            "tests_failed": str(report["test_results"]["failed"]),
            "tests_total": str(report["test_results"]["total"]),
            "phase_rows": phase_rows,
            "agent_rows": agent_rows,
            "bottleneck_items": bottleneck_items,
        }

        html = Template(tmpl_str).safe_substitute(subs)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)
        return html

    # ── Internal helpers ──────────────────────────────────

    def _total_duration(self) -> float:
        starts = [e for e in self.events if e["event_type"] == "session.start"]
        ends = [e for e in self.events if e["event_type"] == "session.end"]
        if starts and ends:
            return (_parse_ts(ends[-1]["timestamp"]) - _parse_ts(starts[0]["timestamp"])).total_seconds()
        if len(self.events) >= 2:
            return (_parse_ts(self.events[-1]["timestamp"]) - _parse_ts(self.events[0]["timestamp"])).total_seconds()
        return 0.0

    def _phase_summaries(self) -> list[dict]:
        enters: dict[int, dict] = {}
        phases: list[dict] = []
        for ev in self.events:
            if ev["event_type"] == "phase.enter":
                enters[ev["phase"]] = ev
            elif ev["event_type"] == "phase.exit":
                pnum = ev["phase"]
                dur = ev.get("data", {}).get("duration_seconds", 0)
                if not dur and pnum in enters:
                    dur = (_parse_ts(ev["timestamp"]) - _parse_ts(enters[pnum]["timestamp"])).total_seconds()
                phases.append({
                    "phase": pnum,
                    "name": PHASE_NAMES.get(pnum, f"Phase {pnum}"),
                    "duration_seconds": dur,
                    "status": "completed",
                    "metrics": ev.get("data", {}),
                })
        return sorted(phases, key=lambda p: p["phase"])

    def _agent_summaries(self) -> list[dict]:
        agents: dict[str, dict] = {}
        for ev in self.events:
            data = ev.get("data", {})
            tid = data.get("task_id", "")
            if ev["event_type"] == "agent.dispatch" and tid:
                agents[tid] = {
                    "task_id": tid,
                    "_dispatch_ts": ev["timestamp"],
                    "status": "dispatched",
                    "files_created": [],
                    "files_modified": [],
                    "retries": 0,
                }
            elif ev["event_type"] == "agent.complete" and tid and tid in agents:
                dt = _parse_ts(ev["timestamp"]) - _parse_ts(agents[tid]["_dispatch_ts"])
                agents[tid]["duration_seconds"] = dt.total_seconds()
                agents[tid]["status"] = data.get("status", "completed")
                agents[tid]["files_created"] = data.get("files_created", [])
                agents[tid]["files_modified"] = data.get("files_modified", [])
            elif ev["event_type"] == "agent.error" and tid and tid in agents:
                agents[tid]["retries"] = agents[tid].get("retries", 0) + 1
        result = list(agents.values())
        for a in result:
            a.pop("_dispatch_ts", None)
            a.setdefault("duration_seconds", 0)
        return result

    def _token_summary(self) -> dict:
        total_in = 0
        total_out = 0
        by_model: dict[str, dict] = {}
        for ev in self.events:
            if ev["event_type"] == "token.usage":
                d = ev.get("data", {})
                inp = d.get("input_tokens", 0)
                out = d.get("output_tokens", 0)
                model = d.get("model", "sonnet")
                total_in += inp
                total_out += out
                if model not in by_model:
                    by_model[model] = {"input": 0, "output": 0, "cost_usd": 0.0}
                by_model[model]["input"] += inp
                by_model[model]["output"] += out
        total_cost = 0.0
        for model, usage in by_model.items():
            pricing = MODEL_PRICING.get(model, MODEL_PRICING["sonnet"])
            cost = (
                usage["input"] / 1_000_000 * pricing["input_per_1m"]
                + usage["output"] / 1_000_000 * pricing["output_per_1m"]
            )
            usage["cost_usd"] = round(cost, 4)
            total_cost += cost
        return {
            "total_input": total_in,
            "total_output": total_out,
            "estimated_cost_usd": round(total_cost, 4),
            "by_model": by_model,
        }

    def _files_summary(self) -> dict:
        created: set[str] = set()
        modified: set[str] = set()
        conflicts: set[str] = set()
        for ev in self.events:
            d = ev.get("data", {})
            if ev["event_type"] == "file.write":
                p = d.get("path", "")
                if d.get("is_new"):
                    created.add(p)
                else:
                    modified.add(p)
            elif ev["event_type"] == "merge.conflict":
                p = d.get("path", "")
                if p:
                    conflicts.add(p)
        return {
            "total_created": len(created),
            "total_modified": len(modified),
            "conflicts": sorted(conflicts),
        }

    def _test_summary(self) -> dict:
        passed = failed = 0
        for ev in self.events:
            if ev["event_type"] == "test.pass":
                passed += ev.get("data", {}).get("count", 1)
            elif ev["event_type"] == "test.fail":
                failed += ev.get("data", {}).get("count", 1)
        return {"passed": passed, "failed": failed, "total": passed + failed}

    # ── Bottleneck checks ─────────────────────────────────

    def _check_slow_agents(self, out: list[dict]) -> None:
        agents = self._agent_summaries()
        durs = [a["duration_seconds"] for a in agents if a["duration_seconds"] > 0]
        if len(durs) < 2:
            return
        avg = sum(durs) / len(durs)
        for a in agents:
            if a["duration_seconds"] > avg * 2:
                ratio = a["duration_seconds"] / avg
                out.append({
                    "type": "slow_agent",
                    "description": f"{a['task_id']} took {a['duration_seconds']:.1f}s ({ratio:.1f}x avg)",
                    "severity": "critical" if ratio > 3 else "warning",
                    "suggestion": f"Consider splitting {a['task_id']} into smaller tasks",
                })

    def _check_slow_phases(self, out: list[dict]) -> None:
        phases = self._phase_summaries()
        durs = [p["duration_seconds"] for p in phases if p["duration_seconds"] > 0]
        if len(durs) < 2:
            return
        avg = sum(durs) / len(durs)
        for p in phases:
            if p["duration_seconds"] > avg * 2:
                out.append({
                    "type": "slow_phase",
                    "description": f"Phase {p['phase']} ({p['name']}) took {p['duration_seconds']:.1f}s ({p['duration_seconds']/avg:.1f}x avg)",
                    "severity": "warning",
                    "suggestion": f"Investigate why {p['name']} phase is slow",
                })

    def _check_retries(self, out: list[dict]) -> None:
        for a in self._agent_summaries():
            if a.get("retries", 0) > 1:
                out.append({
                    "type": "many_retries",
                    "description": f"{a['task_id']} needed {a['retries']} retries",
                    "severity": "critical" if a["retries"] >= 3 else "warning",
                    "suggestion": f"Review error patterns for {a['task_id']}",
                })

    def _check_conflicts(self, out: list[dict]) -> None:
        fs = self._files_summary()
        if fs["conflicts"]:
            out.append({
                "type": "conflict",
                "description": f"{len(fs['conflicts'])} file conflict(s): {', '.join(fs['conflicts'])}",
                "severity": "warning",
                "suggestion": "Consider better task decomposition to avoid shared file modifications",
            })

    def _recommendations(self) -> list[str]:
        recs = [b["suggestion"] for b in self.identify_bottlenecks()]
        return recs or ["No issues found — session ran efficiently"]

    def _compare_phases(self, mine: list[dict], theirs: list[dict]) -> list[dict]:
        other_map = {p["phase"]: p for p in theirs}
        return [
            {
                "phase": p["phase"],
                "name": p["name"],
                "this_duration": p["duration_seconds"],
                "other_duration": other_map[p["phase"]]["duration_seconds"],
                "delta_seconds": round(
                    p["duration_seconds"] - other_map[p["phase"]]["duration_seconds"], 2
                ),
            }
            for p in mine
            if p["phase"] in other_map
        ]
