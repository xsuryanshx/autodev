#!/usr/bin/env python3
"""Run AutoDev Dashboard Server."""
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.server import run_server

if __name__ == "__main__":
    host = os.environ.get("AUTODEV_DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("AUTODEV_DASHBOARD_PORT", 5000))
    log_dir = os.environ.get("AUTODEV_LOG_DIR", ".autodev/logs")
    
    print(f"📊 AutoDev Dashboard")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   Logs: {log_dir}")
    print()
    
    run_server(host=host, port=port)
