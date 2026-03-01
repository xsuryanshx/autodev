"""AutoDev Dashboard Server - serves activity logs over HTTP."""
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request, send_from_directory

app = Flask(__name__)

# Configuration
LOG_DIR = os.environ.get("AUTODEV_LOG_DIR", ".autodev/logs")
PORT = int(os.environ.get("AUTODEV_DASHBOARD_PORT", 5000))
HOST = os.environ.get("AUTODEV_DASHBOARD_HOST", "0.0.0.0")


def get_sessions() -> List[Dict[str, Any]]:
    """Get all sessions from log directory."""
    sessions = []
    log_path = Path(LOG_DIR)
    
    if not log_path.exists():
        return []
    
    for f in log_path.glob("trajectory_*.json"):
        session_id = f.stem.replace("trajectory_", "")
        try:
            with open(f) as fp:
                data = json.load(fp)
                sessions.append({
                    "session_id": session_id,
                    "repo": data.get("repo", "N/A"),
                    "issue": data.get("issue_title", "N/A"),
                    "issue_number": data.get("issue_number"),
                    "status": data.get("status", "unknown"),
                    "events": data.get("total_events", 0),
                    "started": data.get("started_at", "")[:19],
                    "ended": data.get("ended_at", "")[:19] if data.get("ended_at") else "running",
                    "duration": data.get("duration", 0)
                })
        except Exception as e:
            print(f"Error loading {f}: {e}")
    
    return sorted(sessions, key=lambda x: x["session_id"], reverse=True)


def get_trajectory(session_id: str) -> Optional[Dict]:
    """Get trajectory for a session."""
    trajectory_file = Path(LOG_DIR) / f"trajectory_{session_id}.json"
    
    if not trajectory_file.exists():
        return None
    
    with open(trajectory_file) as f:
        return json.load(f)


def get_events(session_id: str) -> List[Dict]:
    events_file = Path(LOG_DIR) / f"events_{session_id}.jsonl"
    
    if not events_file.exists():
        return []
    
    events = []
    with open(events_file) as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    
    return events


# HTML Templates
INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 AutoDev Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a; color: #e2e8f0; min-height: 100vh;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        
        .header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 30px; padding: 20px; background: #1e293b; border-radius: 12px;
        }
        .header h1 { font-size: 28px; color: #f8fafc; }
        .header .refresh { 
            background: #3b82f6; color: white; padding: 10px 20px; 
            border-radius: 8px; text-decoration: none; font-weight: 600;
        }
        
        .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 30px; }
        .stat-card {
            background: #1e293b; padding: 24px; border-radius: 12px; text-align: center;
        }
        .stat-card .value { font-size: 42px; font-weight: bold; color: #3b82f6; }
        .stat-card .label { color: #94a3b8; font-size: 14px; margin-top: 8px; }
        
        .sessions { background: #1e293b; border-radius: 12px; overflow: hidden; }
        .sessions h2 { padding: 20px; border-bottom: 1px solid #334155; }
        
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 16px; text-align: left; border-bottom: 1px solid #334155; }
        th { background: #0f172a; color: #94a3b8; font-weight: 600; font-size: 12px; text-transform: uppercase; }
        td { color: #e2e8f0; }
        
        .status { padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
        .status.completed { background: #22c55e; color: white; }
        .status.running { background: #f59e0b; color: white; }
        .status.failed { background: #ef4444; color: white; }
        
        .link { color: #3b82f6; text-decoration: none; }
        .link:hover { text-decoration: underline; }
        
        .empty { padding: 60px; text-align: center; color: #64748b; }
    </style>
    <meta http-equiv="refresh" content="30">
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 AutoDev Activity Dashboard</h1>
            <a href="/" class="refresh">🔄 Refresh</a>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="value">{{ sessions|length }}</div>
                <div class="label">Total Sessions</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ sessions|selectattr('status', 'equalto', 'completed')|list|length }}</div>
                <div class="label">Completed</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ sessions|selectattr('status', 'equalto', 'running')|list|length }}</div>
                <div class="label">Running</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ sessions|sum(attribute='events') }}</div>
                <div class="label">Total Events</div>
            </div>
        </div>
        
        <div class="sessions">
            <h2>📋 Recent Sessions</h2>
            {% if sessions %}
            <table>
                <thead>
                    <tr>
                        <th>Session</th>
                        <th>Repo</th>
                        <th>Issue</th>
                        <th>Status</th>
                        <th>Events</th>
                        <th>Started</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {% for s in sessions %}
                    <tr>
                        <td>{{ s.session_id }}</td>
                        <td>{{ s.repo }}</td>
                        <td>#{{ s.issue_number }} {{ s.issue[:40] }}</td>
                        <td><span class="status {{ s.status }}">{{ s.status }}</span></td>
                        <td>{{ s.events }}</td>
                        <td>{{ s.started }}</td>
                        <td><a href="/session/{{ s.session_id }}" class="link">View →</a></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty">No sessions yet. Run AutoDev to see activity!</div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

SESSION_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Session {{ session.session_id }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a; color: #e2e8f0; min-height: 100vh;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        
        .header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 30px; padding: 20px; background: #1e293b; border-radius: 12px;
        }
        .header h1 { font-size: 24px; color: #f8fafc; }
        .header a { color: #3b82f6; text-decoration: none; }
        
        .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 30px; }
        .card { background: #1e293b; padding: 20px; border-radius: 12px; text-align: center; }
        .card .value { font-size: 32px; font-weight: bold; color: #3b82f6; }
        .card .label { color: #94a3b8; font-size: 13px; margin-top: 6px; }
        
        .section { background: #1e293b; border-radius: 12px; margin-bottom: 24px; overflow: hidden; }
        .section h2 { padding: 16px 20px; border-bottom: 1px solid #334155; font-size: 18px; }
        
        .timeline { padding: 20px; max-height: 600px; overflow-y: auto; }
        .event { 
            padding: 12px 16px; margin-bottom: 8px; border-radius: 8px; 
            border-left: 3px solid #3b82f6; background: #0f172a;
        }
        .event.success { border-left-color: #22c55e; }
        .event.error { border-left-color: #ef4444; }
        .event.llm { border-left-color: #8b5cf6; }
        .event.git { border-left-color: #f97316; }
        .event.agent { border-left-color: #06b6d4; }
        
        .event .meta { display: flex; gap: 12px; align-items: center; margin-bottom: 6px; }
        .event .time { color: #64748b; font-size: 12px; }
        .event .type { 
            padding: 2px 8px; border-radius: 4px; font-size: 11px; 
            font-weight: bold; background: #334155; color: #e2e8f0;
        }
        .event .desc { color: #cbd5e1; font-size: 14px; }
        
        pre { 
            background: #0f172a; padding: 12px; border-radius: 8px; 
            overflow-x: auto; font-size: 12px; color: #94a3b8; margin-top: 8px;
        }
    </style>
    <meta http-equiv="refresh" content="10">
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 {{ session.session_id }}</h1>
            <a href="/">← Back to Dashboard</a>
        </div>
        
        <div class="grid">
            <div class="card">
                <div class="value">{{ events|length }}</div>
                <div class="label">Total Events</div>
            </div>
            <div class="card">
                <div class="value">{{ llm_calls }}</div>
                <div class="label">LLM Calls</div>
            </div>
            <div class="card">
                <div class="value">{{ tokens|default(0)|round|int }}</div>
                <div class="label">Tokens Used</div>
            </div>
            <div class="card">
                <div class="value">{{ commits }}</div>
                <div class="label">Commits</div>
            </div>
        </div>
        
        <div class="section">
            <h2>📝 Activity Timeline</h2>
            <div class="timeline">
                {% for event in events[-50:]|reverse %}
                <div class="event 
                    {% if 'error' in event.event_type or 'fail' in event.event_type %}error
                    {% elif 'complete' in event.event_type %}success
                    {% elif 'llm' in event.event_type %}llm
                    {% elif 'git' in event.event_type %}git
                    {% elif 'agent' in event.event_type %}agent{% endif %}">
                    <div class="meta">
                        <span class="time">{{ event.timestamp[:19] }}</span>
                        <span class="type">{{ event.event_type }}</span>
                    </div>
                    <div class="desc">{{ event.description }}</div>
                    {% if event.error_message %}
                    <pre>{{ event.error_message }}</pre>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
</body>
</html>
"""


@app.route("/")
def index():
    """Main dashboard page."""
    sessions = get_sessions()
    return render_template_string(INDEX_HTML, sessions=sessions)


@app.route("/api/sessions")
def api_sessions():
    """API endpoint for sessions."""
    return jsonify(get_sessions())


@app.route("/session/<session_id>")
def session_detail(session_id):
    """Session detail page."""
    trajectory = get_trajectory(session_id)
    if not trajectory:
        return "Session not found", 404
    
    events = get_events(session_id)
    
    # Calculate stats
    llm_calls = sum(1 for e in events if "llm" in e.get("event_type", "").lower())
    tokens = sum(
        (e.get("prompt_tokens") or 0) + (e.get("completion_tokens") or 0)
        for e in events if "llm" in e.get("event_type", "").lower()
    )
    commits = sum(1 for e in events if "commit" in e.get("event_type", "").lower())
    
    return render_template_string(
        SESSION_HTML,
        session=trajectory,
        events=events,
        llm_calls=llm_calls,
        tokens=tokens,
        commits=commits
    )


@app.route("/api/session/<session_id>")
def api_session(session_id):
    """API endpoint for a single session."""
    trajectory = get_trajectory(session_id)
    if not trajectory:
        return jsonify({"error": "Session not found"}), 404
    
    events = get_events(session_id)
    return jsonify({
        "trajectory": trajectory,
        "events": events
    })


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "sessions": len(get_sessions())})


def run_server(host: str = HOST, port: int = PORT):
    """Run the dashboard server."""
    print(f"🚀 Starting AutoDev Dashboard on http://{host}:{port}")
    print(f"📁 Log directory: {LOG_DIR}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_server()
