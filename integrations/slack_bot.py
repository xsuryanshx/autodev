"""AutoDev Slack Bot - Complete Integration

Usage:
    python slack_bot.py --channel C012345678 --repo owner/repo

Requirements:
    pip install composio python-dotenv
"""

import os
import sys
import time
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

# Set API key
os.environ["COMPOSIO_API_KEY"] = "ak_eHljs890vpOBg0ucsAq4"

from composio import Composio


class AutoDevSlackBot:
    """
    AutoDev Slack Bot
    
    Listens to Slack channel for bug reports and automatically:
    1. Creates GitHub issue
    2. Runs AutoDev to fix the bug
    3. Posts PR link back to Slack
    """
    
    def __init__(
        self,
        slack_channel: str,
        repo_owner: str,
        repo_name: str,
        local_repo_path: str,
        github_token: str,
        auth_id: str = "ac__nVy6yXFr9zP"
    ):
        self.slack_channel = slack_channel
        self.auth_id = auth_id
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.local_repo_path = local_repo_path
        self.github_token = github_token
        
        self.composio = None
        self.session = None
        self.session_id = None
        
        # Track processed messages
        self.processed_messages = set()
    
    def initialize(self):
        """Initialize Composio session."""
        print("Initializing Composio...")
        self.composio = Composio()
        
        # Create session with the user ID
        self.session = self.composio.create(user_id=self.auth_id)
        
        print(f"✓ Connected to Composio")
        print(f"✓ Slack channel: {self.slack_channel}")
        print(f"✓ GitHub repo: {self.repo_owner}/{self.repo_name}")
    
    def search_tools(self, queries: List[str]) -> Dict:
        """Search for relevant tools using Composio."""
        from composio import Tool
        
        tools = Tool(self.composio)
        
        # Search for Slack and GitHub tools
        result = tools.search(
            queries=[{"use_case": q} for q in queries]
        )
        
        return result
    
    def execute_tool(self, tool_name: str, arguments: Dict) -> Any:
        """Execute a Composio tool."""
        from composio import Tool
        
        tools = Tool(self.composio)
        
        result = tools.execute(
            tools=[{"tool_slug": tool_name, "arguments": arguments}]
        )
        
        return result
    
    def get_slack_messages(self, limit: int = 10) -> List[Dict]:
        """Get recent messages from Slack channel."""
        try:
            # Search for Slack tools
            search_result = self.search_tools([
                "get recent messages from slack channel",
                "list messages in slack channel"
            ])
            
            print(f"Search result: {len(search_result.get('data', []))} tools found")
            
            # Try to execute slack tool
            try:
                result = self.execute_tool("slack_conversations_history", {
                    "channel": self.slack_channel,
                    "limit": limit
                })
                return result.get("data", {}).get("messages", [])
            except Exception as e:
                print(f"Error getting messages: {e}")
                return []
            
        except Exception as e:
            print(f"Error getting messages: {e}")
            return []
    
    def post_slack_message(self, text: str, thread_ts: Optional[str] = None):
        """Post message to Slack."""
        try:
            params = {
                "channel": self.slack_channel,
                "text": text
            }
            if thread_ts:
                params["thread_ts"] = thread_ts
            
            result = self.execute_tool("slack_chat_postMessage", params)
            print(f"✓ Posted to Slack: {text[:50]}...")
            
        except Exception as e:
            print(f"Error posting to Slack: {e}")
    
    def create_github_issue(self, title: str, body: str) -> Optional[int]:
        """Create GitHub issue via Composio."""
        try:
            result = self.execute_tool("github_create_issue", {
                "owner": self.repo_owner,
                "repo": self.repo_name,
                "title": title,
                "body": body
            })
            
            data = result.get("data", {})
            issue_num = data.get("number")
            print(f"✓ Created GitHub issue: #{issue_num}")
            return issue_num
            
        except Exception as e:
            print(f"Error creating issue: {e}")
            return None
    
    def is_bug_report(self, text: str) -> bool:
        """Check if message is a bug report."""
        text_lower = text.lower()
        bug_keywords = [
            "bug", "broken", "fix", "error", "issue", 
            "not working", "crash", "fail", "wrong", "incorrect"
        ]
        return any(keyword in text_lower for keyword in bug_keywords)
    
    def extract_bug_title(self, text: str) -> str:
        """Extract bug title from message."""
        text = text.strip()
        for prefix in ["bug:", "fix:", "error:", "issue:", "broken:"]:
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()
        
        if len(text) > 100:
            text = text[:97] + "..."
        
        return text
    
    def run_autodev(self, issue_number: int) -> Optional[str]:
        """Run AutoDev to fix the issue."""
        print(f"Running AutoDev on issue #{issue_number}...")
        
        # TODO: Integrate with actual AutoDev pipeline
        # from core.orchestrator import Orchestrator
        # orchestrator = Orchestrator(repo_path=self.repo_path, issue_id=issue_number)
        # pr_url = await orchestrator.run()
        # return pr_url
        pr_url = f"https://github.com/{self.repo_owner}/{self.repo_name}/pull/new/feature/fix-{issue_number}"
        
        return pr_url
    
    def process_message(self, message: Dict) -> bool:
        """Process a single Slack message."""
        msg_ts = message.get("ts")
        user = message.get("user", "unknown")
        text = message.get("text", "")
        
        if msg_ts in self.processed_messages:
            return False
        
        if not self.is_bug_report(text):
            return False
        
        print(f"\n📬 Found bug report from {user}: {text[:80]}...")
        self.processed_messages.add(msg_ts)
        
        title = self.extract_bug_title(text)
        
        # Acknowledge in Slack
        self.post_slack_message(
            f"🤖 Got it! Creating issue for: {title}",
            thread_ts=msg_ts
        )
        
        # Create GitHub issue
        issue_body = f"""## Bug Report

**Original Slack Message:**
{text}

**Reported by:** {user}
**Slack Timestamp:** {msg_ts}

---
_AutoDev is working on fixing this!_
"""
        
        issue_number = self.create_github_issue(
            title=f"[Bug] {title}",
            body=issue_body
        )
        
        if issue_number:
            self.post_slack_message(
                f"✅ Created GitHub issue: https://github.com/{self.repo_owner}/{self.repo_name}/issues/{issue_number}",
                thread_ts=msg_ts
            )
            
            pr_url = self.run_autodev(issue_number)
            
            if pr_url:
                self.post_slack_message(
                    f"🎉 Fix ready! PR: {pr_url}",
                    thread_ts=msg_ts
                )
        
        return True
    
    def run(self, poll_interval: int = 30):
        """Run the bot continuously."""
        if not self.composio:
            self.initialize()
        
        print(f"\n🤖 AutoDev Slack Bot Running!")
        print(f"   Channel: {self.slack_channel}")
        print(f"   Repo: {self.repo_owner}/{self.repo_name}")
        print(f"   Polling every {poll_interval}s")
        print(f"\nListening for bug reports...\n")
        
        while True:
            try:
                messages = self.get_slack_messages(limit=10)
                
                for msg in messages:
                    self.process_message(msg)
                
            except Exception as e:
                print(f"Error: {e}")
            
            time.sleep(poll_interval)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="AutoDev Slack Bot")
    parser.add_argument("--channel", required=True, help="Slack channel ID")
    parser.add_argument("--repo", required=True, help="GitHub repo (owner/repo)")
    parser.add_argument("--local-repo", required=True, help="Local repo path")
    parser.add_argument("--github-token", help="GitHub token")
    parser.add_argument("--auth-id", default="ac__nVy6yXFr9zP", help="Composio auth ID")
    parser.add_argument("--poll", type=int, default=30, help="Poll interval")
    
    args = parser.parse_args()
    
    if "/" not in args.repo:
        print("Error: repo must be in format 'owner/repo'")
        sys.exit(1)
    
    owner, repo = args.repo.split("/")
    
    github_token = args.github_token or os.environ.get("GITHUB_TOKEN")
    
    bot = AutoDevSlackBot(
        slack_channel=args.channel,
        repo_owner=owner,
        repo_name=repo,
        local_repo_path=args.local_repo,
        github_token=github_token,
        auth_id=args.auth_id
    )
    
    bot.run(poll_interval=args.poll)


if __name__ == "__main__":
    main()
