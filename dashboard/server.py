"""Dashboard HTTP server with SSE support for real-time agent monitoring."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

try:
    import aiohttp
    from aiohttp import web

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


STATIC_DIR = Path(__file__).parent / "static"


class DashboardServer:
    """HTTP server that serves the dashboard UI and streams events via SSE."""

    def __init__(
        self,
        port: int = 8420,
        events_path: str = ".autodev/events.jsonl",
    ) -> None:
        self.port = port
        self.events_path = events_path

        # SSE client queues — one asyncio.Queue per connected client
        self._clients: list[asyncio.Queue] = []

        # In-memory snapshot of current state
        self._snapshot: dict[str, Any] = {
            "session_id": None,
            "issue": None,
            "phase": None,
            "agents": {},
            "files": {},
            "cost": {"total_tokens": 0, "total_cost": 0.0, "by_model": {}},
            "started_at": None,
        }

        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start HTTP server and SSE endpoint."""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError(
                "aiohttp is required to run the dashboard server. "
                "Install it with: pip install aiohttp"
            )

        self._app = web.Application()
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/events", self._handle_sse)
        self._app.router.add_get("/api/snapshot", self._handle_snapshot)
        self._app.router.add_get("/api/events", self._handle_events_log)
        self._app.router.add_static("/static", STATIC_DIR, show_index=False)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "localhost", self.port)
        await self._site.start()

        print(f"Dashboard: http://localhost:{self.port}")

    async def stop(self) -> None:
        """Graceful shutdown — close SSE clients then tear down the server."""
        # Signal all SSE clients to close
        for queue in list(self._clients):
            await queue.put(None)  # sentinel
        self._clients.clear()

        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        self._site = None
        self._app = None

    def publish_event(self, event: dict) -> None:
        """Push an event dict to all connected SSE clients.

        Also updates the internal snapshot based on event_type.
        """
        self._apply_event_to_snapshot(event)

        serialized = json.dumps(event)
        for queue in list(self._clients):
            try:
                queue.put_nowait(serialized)
            except asyncio.QueueFull:
                pass  # Drop event for slow clients rather than blocking

    def get_snapshot(self) -> dict:
        """Return current state for new client connections."""
        return dict(self._snapshot)

    # ------------------------------------------------------------------
    # Internal snapshot maintenance
    # ------------------------------------------------------------------

    def _apply_event_to_snapshot(self, event: dict) -> None:
        """Update the snapshot based on incoming event."""
        event_type = event.get("event_type", "")
        data = event.get("data", {})

        if event_type == "session.start":
            self._snapshot["session_id"] = data.get("session_id")
            self._snapshot["issue"] = data.get("issue")
            self._snapshot["started_at"] = event.get("timestamp")

        elif event_type == "phase.enter":
            self._snapshot["phase"] = data.get("phase")

        elif event_type == "phase.exit":
            pass  # Phase tracked on enter

        elif event_type == "agent.dispatch":
            agent_id = data.get("agent_id", event.get("source", "unknown"))
            self._snapshot["agents"][agent_id] = {
                "agent_id": agent_id,
                "status": "running",
                "feature": data.get("feature"),
                "subtask": None,
                "subtasks_done": 0,
                "subtasks_total": data.get("subtasks_total", 0),
                "started_at": event.get("timestamp"),
                "elapsed": 0,
            }

        elif event_type == "agent.progress":
            agent_id = data.get("agent_id", event.get("source", "unknown"))
            if agent_id in self._snapshot["agents"]:
                self._snapshot["agents"][agent_id].update(
                    {
                        "subtask": data.get("subtask"),
                        "subtasks_done": data.get("subtasks_done", 0),
                    }
                )

        elif event_type == "agent.complete":
            agent_id = data.get("agent_id", event.get("source", "unknown"))
            if agent_id in self._snapshot["agents"]:
                self._snapshot["agents"][agent_id]["status"] = "completed"

        elif event_type == "agent.error":
            agent_id = data.get("agent_id", event.get("source", "unknown"))
            if agent_id in self._snapshot["agents"]:
                self._snapshot["agents"][agent_id]["status"] = "error"
                self._snapshot["agents"][agent_id]["error"] = data.get("error")

        elif event_type == "file.write":
            path = data.get("path", "unknown")
            agent_id = data.get("agent_id", event.get("source", "unknown"))
            if path not in self._snapshot["files"]:
                self._snapshot["files"][path] = []
            if agent_id not in self._snapshot["files"][path]:
                self._snapshot["files"][path].append(agent_id)

        elif event_type == "token.usage":
            model = data.get("model", "unknown")
            tokens = data.get("tokens", 0)
            cost = data.get("cost", 0.0)
            self._snapshot["cost"]["total_tokens"] += tokens
            self._snapshot["cost"]["total_cost"] += cost
            by_model = self._snapshot["cost"]["by_model"]
            if model not in by_model:
                by_model[model] = {"tokens": 0, "cost": 0.0}
            by_model[model]["tokens"] += tokens
            by_model[model]["cost"] += cost

    # ------------------------------------------------------------------
    # HTTP handlers
    # ------------------------------------------------------------------

    async def _handle_index(self, request: web.Request) -> web.Response:
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return web.FileResponse(index_path)
        return web.Response(text="Dashboard not found", status=404)

    async def _handle_snapshot(self, request: web.Request) -> web.Response:
        return web.json_response(self.get_snapshot())

    async def _handle_events_log(self, request: web.Request) -> web.Response:
        """Return all events from the JSONL file as a JSON array."""
        events: list[dict] = []
        path = Path(self.events_path)
        if path.exists():
            try:
                with open(path) as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                events.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
            except OSError:
                pass
        return web.json_response(events)

    async def _handle_sse(self, request: web.Request) -> web.StreamResponse:
        """SSE endpoint — streams events to connected browser clients."""
        response = web.StreamResponse()
        response.headers["Content-Type"] = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        response.headers["Access-Control-Allow-Origin"] = "*"
        await response.prepare(request)

        # Send initial snapshot so new clients have current state
        snapshot_event = json.dumps(
            {"event_type": "snapshot", "data": self.get_snapshot()}
        )
        await response.write(f"data: {snapshot_event}\n\n".encode())

        # Register this client
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._clients.append(queue)

        try:
            while True:
                # Wait for the next event (with keep-alive pings every 15s)
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Send a comment-based keep-alive ping
                    await response.write(b": ping\n\n")
                    continue

                if item is None:
                    # Server is shutting down
                    break

                await response.write(f"data: {item}\n\n".encode())
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            if queue in self._clients:
                self._clients.remove(queue)

        return response
