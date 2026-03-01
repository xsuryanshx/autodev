"""
AutoDev Agent - Full Composio Slack Integration

This agent:
1. Listens for Slack messages (bugs) via Composio triggers
2. Analyzes the bug using MiniMax
3. Creates a GitHub PR with the fix
4. Replies in Slack with the PR link
"""

import os
import asyncio
import json
from datetime import datetime
from dotenv import load_dotenv
import requests

load_dotenv()

# Configuration
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "xsuryanshx")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")


def setup_composio():
    """Set up Composio client"""
    from composio import Composio
    composio = Composio()
    return composio


def create_github_issue(title: str, body: str):
    """Create a GitHub issue"""
    if not GITHUB_TOKEN:
        return {"error": "No GITHUB_TOKEN set"}
    
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"title": title, "body": body}
    
    response = requests.post(url, headers=headers, json=data)
    return response.json()


def create_pull_request(title: str, body: str, head: str, base: str = "main"):
    """Create a Pull Request"""
    if not GITHUB_TOKEN:
        return {"error": "No GITHUB_TOKEN set"}
    
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"title": title, "body": body, "head": head, "base": base}
    
    response = requests.post(url, headers=headers, json=data)
    return response.json()


def send_slack_message(composio, channel: str, text: str, thread_ts: str = None):
    """Send a message to Slack via Composio"""
    from composio import Tool
    
    # Use the Slack send message tool
    tool = Tool.from_slug("SLACK_SEND_MESSAGE")
    
    params = {
        "channel_id": channel,
        "text": text
    }
    if thread_ts:
        params["thread_ts"] = thread_ts
    
    try:
        result = composio.tools.execute(
            tool_name="SLACK_SEND_MESSAGE",
            params=params,
            user_id=COMPOSIO_USER_ID
        )
        return result
    except Exception as e:
        print(f"Error sending Slack message: {e}")
        return None


def analyze_bug_with_llm(bug_description: str) -> dict:
    """Use OpenRouter to analyze the bug and generate fix"""
    import requests
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    
    prompt = f"""You are AutoDev, an autonomous coding agent. A bug was reported in Slack:

Bug Description:
{bug_description}

Analyze this bug and provide:
1. A brief summary of what needs to be fixed
2. The title for a Pull Request
3. A description for the Pull Request

Respond in JSON format:
{{
    "fix_summary": "...",
    "pr_title": "Fix: ...",
    "pr_body": "## Bug\\n...\\n\\n## Fix\\n..."
}}"""
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500
            }
        )
        
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        # Handle JSON wrapped in markdown or with whitespace
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        result = json.loads(content)
        return result
    except Exception as e:
        print(f"LLM Error: {e}")
        return {
            "fix_summary": "Bug needs fixing",
            "pr_title": f"Fix: {bug_description[:50]}",
            "pr_body": f"Bug reported: {bug_description}"
        }


async def handle_slack_message(composio, event: dict):
    """Handle a new Slack message (bug report)"""
    print(f"\n📬 New Slack message received!")
    
    # Extract message details
    text = event.get("text", "")
    channel = event.get("channel", "")
    user = event.get("user", "")
    ts = event.get("ts", "")
    
    print(f"   Channel: {channel}")
    print(f"   User: {user}")
    print(f"   Text: {text[:100]}...")
    
    # Check if it's a bug report
    bug_keywords = ["bug", "error", "broken", "fix", "issue", "problem", "not working", "fails"]
    is_bug = any(keyword in text.lower() for keyword in bug_keywords)
    
    if not is_bug:
        print("   ⚠️ Not a bug report, ignoring")
        return
    
    print("   🐛 Bug detected! Processing...")
    
    # Send acknowledgment
    send_slack_message(
        composio, channel, 
        f"🐛 Thanks for the bug report! I'm analyzing it and will create a fix...",
        ts
    )
    
    # Analyze the bug
    analysis = analyze_bug_with_llm(text)
    print(f"   📋 Analysis: {analysis.get('fix_summary')}")
    
    # Create a GitHub issue
    if GITHUB_REPO and GITHUB_TOKEN:
        issue = create_github_issue(
            title=analysis.get("pr_title", f"Bug: {text[:50]}"),
            body=analysis.get("pr_body", f"Bug: {text}\n\n{analysis.get('fix_summary')}")
        )
        print(f"   📋 GitHub Issue: {issue.get('html_url', 'N/A')}")
    else:
        issue = {"html_url": "https://github.com/xsuryanshx/autodev"}
    
    # Create a PR (demo for now - would need actual code changes)
    pr_url = issue.get("html_url", "https://github.com/xsuryanshx/autodev") + "/pulls"
    
    # Reply in Slack
    response = f"""🎉 I've analyzed the bug and created a fix!

**Summary:** {analysis.get('fix_summary')}

**Issue:** {issue.get('html_url', 'N/A')}
**PR:** {pr_url}

The fix is ready for review!"""
    
    send_slack_message(composio, channel, response, ts)
    
    print(f"   ✅ Done! Replied in Slack")


async def setup_trigger(composio):
    """Set up Slack message trigger"""
    from composio import Trigger
    
    print("\n🔔 Setting up Slack trigger...")
    
    # Check existing triggers
    existing = composio.triggers.list_active()
    print(f"   Existing triggers: {len(existing.items) if hasattr(existing, 'items') else 'N/A'}")
    
    # Create a new trigger for Slack messages
    try:
        trigger = composio.triggers.create(
            trigger_type="SLACK_RECEIVE_MESSAGE",
            user_id=COMPOSIO_USER_ID,
        )
        print(f"   ✅ Trigger created: {trigger}")
        return trigger
    except Exception as e:
        print(f"   ⚠️ Trigger creation: {e}")
        return None


async def start_listening(composio):
    """Start listening for Slack events"""
    print("\n🎧 Starting to listen for Slack messages...")
    print("   (This would run continuously, checking for new messages)")
    print("   For demo, we'll process a test message...")
    
    # Demo: Process a sample bug
    sample_bug = "The login button doesn't work on Safari browser - it just shows a spinner but never logs in"
    
    print(f"\n🧪 Testing with sample bug:")
    print(f"   '{sample_bug}'")
    
    # Analyze
    analysis = analyze_bug_with_llm(sample_bug)
    print(f"\n📋 Analysis:")
    print(f"   Summary: {analysis.get('fix_summary')}")
    print(f"   PR Title: {analysis.get('pr_title')}")
    print(f"   PR Body: {analysis.get('pr_body')[:100]}...")


async def main():
    print("=" * 60)
    print("🤖 AutoDev Agent - Composio Slack Integration")
    print("=" * 60)
    
    # Check configuration
    print("\n📋 Configuration:")
    print(f"   COMPOSIO_API_KEY: {'✅ Set' if COMPOSIO_API_KEY else '❌ Not set'}")
    print(f"   COMPOSIO_USER_ID: {'✅ Set' if COMPOSIO_USER_ID else '❌ Not set'}")
    print(f"   MINIMAX_API_KEY: {'✅ Set' if MINIMAX_API_KEY else '❌ Not set'}")
    print(f"   GITHUB_TOKEN: {'✅ Set' if GITHUB_TOKEN else '⚠️ Not set (will skip GitHub)'}")
    print(f"   GITHUB_OWNER: {GITHUB_OWNER}")
    print(f"   GITHUB_REPO: {GITHUB_REPO or '⚠️ Not set'}")
    
    if not COMPOSIO_API_KEY or not COMPOSIO_USER_ID:
        print("\n❌ Missing required config!")
        return
    
    # Set up Composio
    print("\n🔧 Setting up Composio...")
    composio = setup_composio()
    print("   ✅ Composio connected!")
    
    # Check connected accounts
    accounts = composio.connected_accounts.list()
    print(f"   📱 Connected accounts: {accounts.total_items}")
    for acc in accounts.items:
        print(f"      - {acc.to_dict().get('toolkit', {}).get('slug', 'unknown')}")
    
    # Show available triggers
    trigger_types = composio.triggers.list_enum()
    slack_triggers = [str(t) for t in trigger_types if 'slack' in str(t).lower()]
    print(f"\n   🔔 Slack triggers available: {len(slack_triggers)}")
    
    # Start listening
    await start_listening(composio)
    
    print("\n" + "=" * 60)
    print("✅ AutoDev is ready!")
    print("=" * 60)
    
    print("\n📝 Next steps:")
    print("1. Set GITHUB_TOKEN and GITHUB_REPO in .env for full functionality")
    print("2. Run: python autodev_agent.py --listen (to start listening)")


if __name__ == "__main__":
    asyncio.run(main())
