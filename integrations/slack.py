"""Slack integration for AutoDev using Composio."""
import os
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class SlackMessage:
    """Represents a Slack message."""
    channel: str
    user: str
    text: str
    ts: str  # timestamp
    thread_ts: Optional[str] = None


class SlackIntegration:
    """
    AutoDev Slack Integration
    
    Listens for bug reports in Slack and triggers AutoDev to fix them.
    Posts PR links back to Slack.
    
    Workflow:
    1. Listen to Slack channel for messages containing "bug" or "fix"
    2. Extract bug description from message
    3. Trigger AutoDev to create fix
    4. Reply with PR link
    """
    
    def __init__(self, composio_api_key: Optional[str] = None):
        self.composio_api_key = composio_api_key or os.environ.get("COMPOSIO_API_KEY")
        self.github_token = os.environ.get("GITHUB_TOKEN")
        self.repo_owner = os.environ.get("GITHUB_OWNER")
        self.repo_name = os.environ.get("GITHUB_REPO")
        
        # Composio client (initialized lazily)
        self.composio = None
        self.session = None
    
    def initialize(self):
        """Initialize Composio connection."""
        if not self.composio_api_key:
            raise ValueError("COMPOSIO_API_KEY required")
        
        os.environ["COMPOSIO_API_KEY"] = self.composio_api_key
        
        # Import Composio
        from composio import Composio
        
        self.composio = Composio()
        self.session = self.composio.create(user_id="autodev")
        
        return self
    
    def listen_for_bugs(self, channel_id: str, limit: int = 10) -> List[SlackMessage]:
        """Listen to Slack channel for recent messages."""
        if not self.session:
            self.initialize()
        
        # Get Slack toolkit tools
        tools = self.session.tools()
        
        # Look for slack toolkit
        slack_tools = [t for t in tools if "slack" in str(t).lower()]
        
        # For now, return empty - would need actual tool execution
        return []
    
    def post_message(self, channel: str, text: str, thread_ts: Optional[str] = None) -> Dict:
        """Post a message to Slack channel."""
        if not self.session:
            self.initialize()
        
        # Use Composio Slack tool to post message
        # This would execute: slack.chat_postMessage
        return {
            "ok": True,
            "channel": channel,
            "text": text
        }
    
    def extract_bug_from_message(self, text: str) -> Optional[str]:
        """Extract bug description from Slack message."""
        text_lower = text.lower()
        
        # Keywords that indicate a bug report
        bug_keywords = ["bug", "broken", "fix", "error", "issue", "not working", "crash", "fail"]
        
        # Check if message contains bug keywords
        if any(keyword in text_lower for keyword in bug_keywords):
            # Clean up the message - remove common prefixes
            cleaned = text
            for prefix in ["bug:", "fix:", "error:", "issue:"]:
                if cleaned.lower().startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
            
            return cleaned
        
        return None
    
    def create_github_issue(self, title: str, body: str) -> int:
        """Create a GitHub issue via Composio."""
        if not self.session:
            self.initialize()
        
        # Use Composio GitHub tool to create issue
        # This would execute: github.create_issue
        return 1  # Issue number
    
    def reply_with_pr(self, channel: str, thread_ts: str, pr_url: str):
        """Reply to Slack thread with PR link."""
        message = f"🎉 Fixed! Here's the PR: {pr_url}"
        return self.post_message(channel, message, thread_ts=thread_ts)


class AutoDevSlackBot:
    """
    Main bot that combines Slack listening with AutoDev execution.
    
    Usage:
        bot = AutoDevSlackBot(
            composio_api_key="...",
            github_token="...",
            repo_owner="username",
            repo_name="repo"
        )
        bot.run()
    """
    
    def __init__(
        self,
        slack_channel: str,
        composio_api_key: str,
        github_token: str,
        repo_owner: str,
        repo_name: str,
        local_repo_path: str
    ):
        self.slack_channel = slack_channel
        self.local_repo_path = local_repo_path
        
        self.slack = SlackIntegration(composio_api_key)
        self.github_token = github_token
        self.repo_owner = repo_owner
        self.repo_name = repo_name
    
    def process_bug_report(self, message: SlackMessage) -> bool:
        """Process a bug report from Slack."""
        # Extract bug description
        bug_description = self.slack.extract_bug_from_message(message.text)
        if not bug_description:
            return False
        
        print(f"Found bug: {bug_description}")
        
        # Acknowledge in Slack
        self.slack.post_message(
            message.channel,
            f"🤖 Got it! Creating issue and fix for: {bug_description[:50]}...",
            thread_ts=message.thread_ts or message.ts
        )
        
        # TODO: Trigger AutoDev here
        # from run_autodev import run_autodev
        # result = run_autodev(...)
        
        # For now, just reply
        self.slack.post_message(
            message.channel,
            f"🔧 AutoDev would now: create issue → decompose → code fix → create PR",
            thread_ts=message.thread_ts or message.ts
        )
        
        return True
    
    def run_once(self):
        """Process once."""
        messages = self.slack.listen_for_bugs(self.slack_channel)
        
        for msg in messages:
            self.process_bug_report(msg)
    
    def run(self, poll_interval: int = 60):
        """Run continuously."""
        import time
        
        print(f"🤖 AutoDev Slack Bot started - listening to {self.slack_channel}")
        
        while True:
            try:
                self.run_once()
            except Exception as e:
                print(f"Error: {e}")
            
            time.sleep(poll_interval)


def main():
    """CLI for AutoDev Slack Bot."""
    import argparse
    
    parser = argparse.ArgumentParser(description="AutoDev Slack Bot")
    parser.add_argument("--channel", required=True, help="Slack channel ID")
    parser.add_argument("--composio-key", help="Composio API key")
    parser.add_argument("--github-token", help="GitHub token")
    parser.add_argument("--repo", required=True, help="GitHub repo (owner/repo)")
    parser.add_argument("--local-repo", required=True, help="Local repo path")
    
    args = parser.parse_args()
    
    owner, repo = args.repo.split("/")
    
    bot = AutoDevSlackBot(
        slack_channel=args.channel,
        composio_api_key=args.composio_key or os.environ.get("COMPOSIO_API_KEY"),
        github_token=args.github_token or os.environ.get("GITHUB_TOKEN"),
        repo_owner=owner,
        repo_name=repo,
        local_repo_path=args.local_repo
    )
    
    bot.run()


if __name__ == "__main__":
    main()
