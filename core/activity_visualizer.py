"""Visualizer for AutoDev activity logs - generates HTML reports."""
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import Counter


class ActivityVisualizer:
    """
    Generate visual reports from activity logs.
    
    Provides:
    - HTML dashboard
    - Timeline view
    - Statistics summary
    - Error analysis
    """
    
    def __init__(self, log_dir: str = ".autodev/logs"):
        self.log_dir = Path(log_dir)
    
    def generate_dashboard(self, session_id: str, output_path: Optional[str] = None) -> str:
        """Generate HTML dashboard for a session."""
        # Load trajectory
        trajectory = self._load_trajectory(session_id)
        events = trajectory.get("events", [])
        
        # Generate HTML
        html = self._generate_html(trajectory, events)
        
        # Save to file
        if output_path is None:
            output_path = str(self.log_dir / f"dashboard_{session_id}.html")
        
        with open(output_path, "w") as f:
            f.write(html)
        
        return output_path
    
    def _load_trajectory(self, session_id: str) -> Dict:
        """Load trajectory from file."""
        trajectory_file = self.log_dir / f"trajectory_{session_id}.json"
        
        if not trajectory_file.exists():
            raise FileNotFoundError(f"Trajectory not found: {session_id}")
        
        with open(trajectory_file) as f:
            return json.load(f)
    
    def _generate_html(self, trajectory: Dict, events: List[Dict]) -> str:
        """Generate full HTML report."""
        
        # Calculate stats
        stats = self._calculate_stats(events)
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoDev Activity - {trajectory.get('session_id', 'Unknown')}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a; color: #e2e8f0; line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        
        h1, h2, h3 {{ color: #f8fafc; margin-bottom: 16px; }}
        h1 {{ font-size: 28px; border-bottom: 2px solid #3b82f6; padding-bottom: 12px; }}
        
        .header {{ background: #1e293b; padding: 24px; border-radius: 12px; margin-bottom: 24px; }}
        .header h1 {{ margin-bottom: 8px; }}
        .header .meta {{ color: #94a3b8; font-size: 14px; }}
        
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .card {{ 
            background: #1e293b; padding: 20px; border-radius: 12px; 
            border: 1px solid #334155;
        }}
        .card .value {{ font-size: 36px; font-weight: bold; color: #3b82f6; }}
        .card .label {{ color: #94a3b8; font-size: 14px; margin-top: 4px; }}
        
        .section {{ background: #1e293b; padding: 24px; border-radius: 12px; margin-bottom: 24px; }}
        
        .timeline {{ position: relative; padding-left: 24px; }}
        .timeline::before {{
            content: ''; position: absolute; left: 8px; top: 0; bottom: 0;
            background: #334155; width: 2px;
        }}
        .event {{ 
            position: relative; padding: 12px 16px; margin-bottom: 12px; 
            background: #0f172a; border-radius: 8px; border-left: 3px solid;
        }}
        .event.success {{ border-left-color: #22c55e; }}
        .event.error {{ border-left-color: #ef4444; }}
        .event.warning {{ border-left-color: #f59e0b; }}
        .event.info {{ border-left-color: #3b82f6; }}
        
        .event .time {{ color: #64748b; font-size: 12px; }}
        .event .type {{ 
            display: inline-block; padding: 2px 8px; border-radius: 4px; 
            font-size: 11px; font-weight: bold; margin: 4px 0;
        }}
        .event .type.task {{ background: #3b82f6; color: white; }}
        .event .type.llm {{ background: #8b5cf6; color: white; }}
        .event .type.git {{ background: #f97316; color: white; }}
        .event .type.agent {{ background: #06b6d4; color: white; }}
        .event .type.error {{ background: #ef4444; color: white; }}
        
        .event .desc {{ color: #e2e8f0; margin-top: 4px; }}
        
        .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
        .stat {{ text-align: center; padding: 12px; background: #0f172a; border-radius: 8px; }}
        .stat .num {{ font-size: 24px; font-weight: bold; color: #3b82f6; }}
        .stat .lbl {{ font-size: 12px; color: #64748b; }}
        
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ color: #94a3b8; font-weight: 600; font-size: 12px; text-transform: uppercase; }}
        td {{ color: #e2e8f0; }}
        
        .badge {{ 
            padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;
        }}
        .badge.completed {{ background: #22c55e; color: white; }}
        .badge.failed {{ background: #ef4444; color: white; }}
        .badge.running {{ background: #f59e0b; color: white; }}
        
        pre {{ 
            background: #0f172a; padding: 12px; border-radius: 8px; 
            overflow-x: auto; font-size: 12px; color: #94a3b8;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 AutoDev Activity Report</h1>
            <div class="meta">
                Session: {trajectory.get('session_id', 'N/A')} | 
                Repo: {trajectory.get('repo', 'N/A')} |
                Issue: #{trajectory.get('issue_number', 'N/A')} - {trajectory.get('issue_title', 'N/A')}
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <div class="value">{stats['total_events']}</div>
                <div class="label">Total Events</div>
            </div>
            <div class="card">
                <div class="value">{stats['llm_calls']}</div>
                <div class="label">LLM Calls</div>
            </div>
            <div class="card">
                <div class="value">{stats['tokens_used']:,}</div>
                <div class="label">Tokens Used</div>
            </div>
            <div class="card">
                <div class="value">{stats['commits']}</div>
                <div class="label">Commits</div>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <div class="value">{stats['tasks_created']}</div>
                <div class="label">Tasks Created</div>
            </div>
            <div class="card">
                <div class="value">{stats['tasks_completed']}</div>
                <div class="label">Tasks Completed</div>
            </div>
            <div class="card">
                <div class="value">{stats['tasks_failed']}</div>
                <div class="label">Tasks Failed</div>
            </div>
            <div class="card">
                <div class="value">{stats['duration']:.1f}s</div>
                <div class="label">Duration</div>
            </div>
        </div>
        
        <div class="section">
            <h2>📊 Task Summary</h2>
            <div class="stats-grid">
                <div class="stat">
                    <div class="num">{stats['agents_spawned']}</div>
                    <div class="lbl">Agents Spawned</div>
                </div>
                <div class="stat">
                    <div class="num">{stats['files_created']}</div>
                    <div class="lbl">Files Created</div>
                </div>
                <div class="stat">
                    <div class="num">{stats['prs_created']}</div>
                    <div class="lbl">PRs Created</div>
                </div>
                <div class="stat">
                    <div class="num">{stats['errors']}</div>
                    <div class="lbl">Errors</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>📝 Activity Timeline</h2>
            <div class="timeline">
"""
        
        # Add events
        for event in events[-50:]:  # Last 50 events
            event_type = event.get('event_type', 'unknown')
            timestamp = event.get('timestamp', '')[:19]
            description = event.get('description', '')
            
            # Determine style
            if 'error' in event_type.lower() or 'fail' in event_type.lower():
                style_class = 'error'
            elif 'complete' in event_type.lower() or 'success' in event_type.lower():
                style_class = 'success'
            elif 'warning' in event_type.lower():
                style_class = 'warning'
            else:
                style_class = 'info'
            
            # Get type badge
            type_category = 'info'
            if 'task' in event_type.lower():
                type_category = 'task'
            elif 'llm' in event_type.lower():
                type_category = 'llm'
            elif 'git' in event_type.lower():
                type_category = 'git'
            elif 'agent' in event_type.lower():
                type_category = 'agent'
            elif 'error' in event_type.lower():
                type_category = 'error'
            
            html += f"""
                <div class="event {style_class}">
                    <div class="time">{timestamp}</div>
                    <span class="type {type_category}">{event_type}</span>
                    <div class="desc">{description}</div>
                </div>
"""
        
        html += """
            </div>
        </div>
        
        <div class="section">
            <h2>📈 LLM Token Usage</h2>
"""
        
        # Add LLM stats
        llm_events = [e for e in events if 'llm' in e.get('event_type', '').lower()]
        if llm_events:
            html += """
            <table>
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Model</th>
                        <th>Prompt Tokens</th>
                        <th>Completion Tokens</th>
                        <th>Total</th>
                        <th>Latency</th>
                    </tr>
                </thead>
                <tbody>
"""
            for event in llm_events[-10:]:
                html += f"""
                    <tr>
                        <td>{event.get('timestamp', '')[:19]}</td>
                        <td>{event.get('model', 'N/A')}</td>
                        <td>{event.get('prompt_tokens') or 0}</td>
                        <td>{event.get('completion_tokens') or 0}</td>
                        <td>{(event.get('prompt_tokens') or 0) + (event.get('completion_tokens') or 0)}</td>
                        <td>{event.get('latency_ms') or 0}ms</td>
                    </tr>
"""
            html += """
                </tbody>
            </table>
"""
        else:
            html += "<p>No LLM calls recorded.</p>"
        
        html += """
        </div>
        
        <div class="section">
            <h2>❌ Errors</h2>
"""
        
        # Add errors
        error_events = [e for e in events if 'error' in e.get('event_type', '').lower()]
        if error_events:
            for event in error_events:
                html += f"""
                <div class="event error">
                    <div class="time">{event.get('timestamp', '')[:19]}</div>
                    <div class="desc">{event.get('description', '')}</div>
                    <pre>{event.get('error_message', 'No details')}</pre>
                </div>
"""
        else:
            html += "<p>No errors recorded! 🎉</p>"
        
        html += """
        </div>
    </div>
</body>
</html>
"""
        
        return html
    
    def _calculate_stats(self, events: List[Dict]) -> Dict:
        """Calculate statistics from events."""
        stats = {
            'total_events': len(events),
            'llm_calls': 0,
            'tokens_used': 0,
            'commits': 0,
            'tasks_created': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'agents_spawned': 0,
            'files_created': 0,
            'prs_created': 0,
            'errors': 0,
            'duration': 0
        }
        
        # Calculate duration
        if events:
            try:
                start = datetime.fromisoformat(events[0].get('timestamp', '').replace('Z', '+00:00'))
                end = datetime.fromisoformat(events[-1].get('timestamp', '').replace('Z', '+00:00'))
                stats['duration'] = (end - start).total_seconds()
            except:
                pass
        
        # Count events
        for event in events:
            event_type = event.get('event_type', '')
            
            if 'llm_call_end' in event_type:
                stats['llm_calls'] += 1
                stats['tokens_used'] += event.get('prompt_tokens', 0) + event.get('completion_tokens', 0)
            elif 'git_commit' in event_type:
                stats['commits'] += 1
            elif 'task_created' in event_type:
                stats['tasks_created'] += 1
            elif 'task_completed' in event_type:
                stats['tasks_completed'] += 1
            elif 'task_failed' in event_type:
                stats['tasks_failed'] += 1
            elif 'agent_spawned' in event_type:
                stats['agents_spawned'] += 1
            elif 'code_written' in event_type:
                stats['files_created'] += 1
            elif 'pr_created' in event_type:
                stats['prs_created'] += 1
            elif 'error' in event_type.lower():
                stats['errors'] += 1
        
        return stats
    
    def list_sessions(self) -> List[Dict]:
        """List all available sessions."""
        sessions = []
        
        for f in self.log_dir.glob("trajectory_*.json"):
            session_id = f.stem.replace("trajectory_", "")
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    sessions.append({
                        "session_id": session_id,
                        "repo": data.get("repo", "N/A"),
                        "issue": data.get("issue_title", "N/A"),
                        "status": data.get("status", "N/A"),
                        "events": data.get("total_events", 0)
                    })
            except:
                pass
        
        return sorted(sessions, key=lambda x: x['session_id'], reverse=True)


def main():
    """CLI for generating reports."""
    import argparse
    
    parser = argparse.ArgumentParser(description="AutoDev Activity Visualizer")
    parser.add_argument("--log-dir", default=".autodev/logs", help="Log directory")
    parser.add_argument("--session", help="Session ID to visualize")
    parser.add_argument("--list", action="store_true", help="List all sessions")
    parser.add_argument("--output", help="Output HTML file path")
    
    args = parser.parse_args()
    
    viz = ActivityVisualizer(args.log_dir)
    
    if args.list:
        sessions = viz.list_sessions()
        print(f"Found {len(sessions)} sessions:\n")
        for s in sessions:
            print(f"  {s['session_id']}: {s['repo']} - {s['issue']} ({s['events']} events)")
    elif args.session:
        output = viz.generate_dashboard(args.session, args.output)
        print(f"Generated: {output}")
    else:
        print("Use --list to see sessions or --session <id> to generate report")


if __name__ == "__main__":
    main()
