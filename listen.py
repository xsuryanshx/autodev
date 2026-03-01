"""
AutoDev Agent - Full Composio Slack Integration
Listens for bugs in Slack and asks before creating PRs
"""

import os
import asyncio
import json
import re
import subprocess
from dotenv import load_dotenv
import requests

load_dotenv()

# Configuration
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "xsuryanshx")
GITHUB_REPO = os.getenv("GITHUB_REPO", "autodev")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "")

# Workspace for cloned repos
REPO_WORKSPACE = "/home/ubuntu/.openclaw/workspace/cloned_repos"


def setup_composio():
    from composio import Composio
    composio = Composio()
    return composio


def analyze_bug_with_llm(bug_description: str, repo_url: str = None) -> dict:
    """Use OpenRouter to analyze the bug and generate fix plan"""
    prompt = f"""You are AutoDev, an autonomous coding agent. A bug was reported in Slack:

Bug Description:
{bug_description}

Repository (if mentioned): {repo_url or 'Not specified'}

Analyze this bug and provide:
1. A brief summary of what needs to be fixed
2. The title for a Pull Request
3. A description for the Pull Request
4. What files might need to be changed

Respond in JSON format:
{{
    "fix_summary": "...",
    "pr_title": "Fix: ...",
    "pr_body": "## Bug\\n...\\n\\n## Fix\\n...",
    "files_to_check": ["file1.py", "file2.js"]
}}"""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
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
            "pr_body": f"Bug reported: {bug_description}",
            "files_to_check": []
        }


def extract_repo_url(text: str) -> str:
    """Extract GitHub repo URL from text"""
    # Match GitHub URLs
    patterns = [
        r'https?://github\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)',
        r'github\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            owner, repo = match.groups()
            # Remove .git if present
            repo = repo.replace('.git', '')
            return f"https://github.com/{owner}/{repo}"
    
    return None


def create_github_issue(title: str, body: str, owner: str, repo: str):
    """Create a GitHub issue"""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"title": title, "body": body}

    response = requests.post(url, headers=headers, json=data)
    return response.json()


def clone_repo(repo_url: str, local_path: str):
    """Clone a GitHub repository"""
    try:
        # Use GitHub token for private repos
        repo_url_with_token = repo_url.replace("https://", f"https://{GITHUB_TOKEN}@")
        
        subprocess.run(["rm", "-rf", local_path], check=False)
        subprocess.run(["git", "clone", "--depth", "1", repo_url_with_token, local_path], 
                      check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"Clone error: {e}")
        return False


def send_slack_message(composio, channel: str, text: str, thread_ts: str = None):
    """Send a message to Slack via Composio"""
    params = {"channel_id": channel, "text": text}
    if thread_ts:
        params["thread_ts"] = thread_ts

    try:
        result = composio.tools.execute(
            slug="SLACK_SEND_MESSAGE",
            arguments=params,
            user_id=COMPOSIO_USER_ID,
            dangerously_skip_version_check=True
        )
        return result
    except Exception as e:
        print(f"Error sending Slack message: {e}")
        return None


def fetch_slack_messages(composio, channel: str, limit: int = 10):
    """Fetch recent messages from a Slack channel"""
    try:
        result = composio.tools.execute(
            slug="SLACK_FETCH_CONVERSATION_HISTORY",
            arguments={"channel": channel, "limit": limit},
            user_id=COMPOSIO_USER_ID,
            dangerously_skip_version_check=True
        )
        return result
    except Exception as e:
        print(f"Error fetching messages: {e}")
        return None


# Track processed messages and pending approvals
# Key: (channel, thread_ts) -> approval data
processed_messages = set()
pending_approvals = {}  # {thread_ts: {repo_url, analysis, bug_description, channel}}


async def check_for_bugs(composio):
    """Check Slack channel for new bug reports"""
    global processed_messages, pending_approvals

    if not SLACK_CHANNEL_ID:
        print("⚠️ No SLACK_CHANNEL_ID configured")
        return

    print(f"\n🔍 Checking channel {SLACK_CHANNEL_ID}...")

    try:
        messages = fetch_slack_messages(composio, SLACK_CHANNEL_ID, limit=20)
        
        if not messages:
            return

        msg_data = messages
        if isinstance(msg_data, dict) and 'data' in msg_data:
            msg_data = msg_data['data']
        
        msg_list = msg_data.get('messages', [])
        if not msg_list:
            return

        print(f"   Found {len(msg_list)} messages")

        # Process messages in reverse (oldest first)
        for msg in reversed(msg_list):
            msg_id = msg.get("ts")
            text = msg.get("text", "")
            
            if not text or not msg_id:
                continue

            # Get thread info - replies use thread_ts
            thread_ts = msg.get("thread_ts", msg_id)
            
            # Check for approval keywords (in thread or direct)
            approval_keywords = ["yes", "approve", "go ahead", "do it", "proceed", "make the fix", "create pr"]
            is_approval = any(keyword in text.lower() for keyword in approval_keywords)
            
            if is_approval and thread_ts in pending_approvals:
                print(f"   ✅ Approval received in thread {thread_ts}!")
                # Process the approval
                approval_data = pending_approvals.pop(thread_ts)
                await process_approval(composio, approval_data)
                continue

            if msg_id in processed_messages:
                continue

            # Check if it's a bug
            bug_keywords = ["bug", "error", "broken", "fix", "issue", "problem", "not working", "fails", "crash"]
            is_bug = any(keyword in text.lower() for keyword in bug_keywords)

            if is_bug:
                print(f"   🐛 Bug detected!")
                processed_messages.add(msg_id)

                # Extract repo URL
                repo_url = extract_repo_url(text)
                print(f"   📦 Repo: {repo_url}")

                # Analyze with LLM
                analysis = analyze_bug_with_llm(text, repo_url)
                print(f"   📋 Analysis: {analysis.get('fix_summary')}")

                # Ask for approval in Slack
                response = f"""🐛 **Bug detected!**

**Summary:** {analysis.get('fix_summary')}

**Files to check:** {', '.join(analysis.get('files_to_check', [])[:3]) or 'Need to explore'}

**Repository:** {repo_url or GITHUB_OWNER + '/' + GITHUB_REPO}

---

Do you want me to create a fix and PR?

👉 Reply with **"yes"**, **"approve"**, or **"go ahead"** to proceed
👉 Reply with **"no"** or **"skip"** to cancel"""

                send_slack_message(composio, SLACK_CHANNEL_ID, response, msg_id)
                
                # Store for later approval (use thread_ts as key)
                thread_ts = msg.get("thread_ts", msg_id)
                if repo_url:
                    pending_approvals[thread_ts] = {
                        "repo_url": repo_url,
                        "analysis": analysis,
                        "bug_description": text,
                        "original_msg_id": msg_id,
                        "channel": SLACK_CHANNEL_ID
                    }

    except Exception as e:
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()


async def process_approval(composio, approval_data):
    """Process an approved bug fix request"""
    repo_url = approval_data["repo_url"]
    analysis = approval_data["analysis"]
    bug_description = approval_data["bug_description"]
    original_msg_id = approval_data["original_msg_id"]

    # Extract owner and repo from URL
    match = re.search(r'github\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)', repo_url)
    if not match:
        send_slack_message(composio, SLACK_CHANNEL_ID, 
                          "❌ Could not parse repo URL", original_msg_id)
        return

    owner, repo = match.groups()
    repo = repo.replace('.git', '')
    local_path = f"{REPO_WORKSPACE}/{owner}-{repo}"

    # Acknowledge
    send_slack_message(composio, SLACK_CHANNEL_ID, 
                      f"🚀 Starting work on {repo_url}...", original_msg_id)

    # Clone the repo
    print(f"   📦 Cloning {repo_url}...")
    if not clone_repo(repo_url, local_path):
        send_slack_message(composio, SLACK_CHANNEL_ID, 
                          f"❌ Failed to clone {repo_url}", original_msg_id)
        return

    # In a full implementation, we would:
    # 1. Analyze the codebase
    # 2. Make code changes
    # 3. Create a branch
    # 4. Commit changes
    # 5. Create PR
    
    # For now, just create an issue as a demo
    issue = create_github_issue(
        title=analysis.get("pr_title", f"Bug: {bug_description[:50]}"),
        body=analysis.get("pr_body", f"Bug: {bug_description}\n\n{analysis.get('fix_summary')}"),
        owner=owner,
        repo=repo
    )

    issue_url = issue.get("html_url", "N/A")
    
    send_slack_message(composio, SLACK_CHANNEL_ID, 
                      f"""✅ Done!

**GitHub Issue:** {issue_url}

(PR creation would happen next - implementing code changes)""", 
                      original_msg_id)


async def main():
    print("=" * 60)
    print("🤖 AutoDev Agent - Listening for Bugs")
    print("=" * 60)

    print(f"\n📋 Config:")
    print(f"   Channel: {SLACK_CHANNEL_ID}")
    print(f"   GitHub: {GITHUB_OWNER}/{GITHUB_REPO}")

    composio = setup_composio()
    print("   Composio: ✅ Connected")

    print("\n🎧 Listening for bugs...")
    print("   - Post a bug with GitHub URL to start")
    print("   - Reply 'yes' to approve fixes")

    await check_for_bugs(composio)

    print("\n✅ Done checking!")


if __name__ == "__main__":
    asyncio.run(main())
