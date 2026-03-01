"""Reviewer Agent - Agent-to-agent code review for AutoDev."""
import os
import subprocess
from typing import Dict, Any, Optional, List, Tuple
from utils.logger import get_logger


class ReviewerAgent:
    """
    Reviewer Agent - performs code reviews on behalf of other agents.
    
    This enables agent-to-agent code review:
    1. Coder agent completes a PR
    2. Reviewer agent reviews the changes
    3. If issues found → Coder fixes them
    4. Loop until reviewer approves
    
    Responsibilities:
    - Review code changes (diff)
    - Check for bugs, code quality
    - Verify tests exist and pass
    - Check style consistency
    - Approve or request changes
    """
    
    OPENCODE_PATH = "opencode"
    
    def __init__(self, agent_id: str = "reviewer", config: Optional[Dict[str, Any]] = None):
        self.agent_id = agent_id
        self.config = config or {}
        self.logger = get_logger(f"autodev.reviewer.{agent_id}")
        self.review_prompt_template = """
You are a code reviewer. Review the following changes and provide feedback.

## Changes to Review:
{changes}

## Context:
- Branch: {branch}
- Base: {base}

## Review Criteria:
1. **Correctness** - Does the code work as intended?
2. **Bugs** - Are there potential bugs or edge cases?
3. **Tests** - Are tests included and do they pass?
4. **Code Quality** - Is the code clean and readable?
5. **Style** - Does it follow project conventions?
6. **Security** - Any security issues?

## Output Format:
Provide your review in this format:

### APPROVED
If the code is good and ready to merge.

### CHANGES REQUESTED
If changes are needed. List specific issues:
1. [Issue description]
2. [Issue description]

### MINOR SUGGESTIONS
Optional improvements that aren't blockers.

Be thorough but practical. Focus on real issues, not style preferences.
"""
    
    def initialize(self, github_client=None):
        """Initialize with dependencies."""
        self.github_client = github_client
        self.logger.info(f"Reviewer Agent {self.agent_id} initialized")
    
    def review_branch(
        self,
        repo_path: str,
        branch: str,
        base: str = "main",
        max_retries: int = 3
    ) -> Tuple[str, List[str], Dict[str, Any]]:
        """
        Review changes in a branch compared to base.
        
        Args:
            repo_path: Local path to repository
            branch: Branch to review
            base: Base branch to compare against
            max_retries: Max review iterations
            
        Returns:
            Tuple of (final_status, issues_list, metadata)
        """
        self.logger.info(f"Starting review of branch '{branch}' vs '{base}'")
        
        issues_found = []
        metadata = {
            "branch": branch,
            "base": base,
            "iterations": 0,
            "issues": []
        }
        
        for iteration in range(1, max_retries + 1):
            metadata["iterations"] = iteration
            
            # Get the diff
            changes = self._get_diff(repo_path, base, branch)
            
            if not changes:
                self.logger.warning(f"No changes found in {branch}")
                break
            
            # Review the changes
            self.logger.info(f"Iteration {iteration}: Reviewing {len(changes.split('---'))} files changed")
            
            review_result = self._review_changes(changes, branch, base)
            
            status = review_result["status"]
            feedback = review_result["feedback"]
            
            if status == "APPROVED":
                self.logger.info(f"✅ Review approved on iteration {iteration}")
                return "approved", issues_found, metadata
            
            # Collect issues
            if feedback:
                issues = self._parse_issues(feedback)
                issues_found.extend(issues)
                metadata["issues"].extend(issues)
                
                self.logger.warning(f"❌ Changes requested on iteration {iteration}: {len(issues)} issues")
                for issue in issues:
                    self.logger.info(f"   - {issue}")
            
            # Ask coder to fix (in real implementation, this would trigger the coder)
            # For now, return the issues for human/agent to address
            self.logger.info(f"Changes requested. Issues to fix: {issues}")
            
            # If this is the last iteration, return what we have
            if iteration == max_retries:
                self.logger.warning(f"Max retries ({max_retries}) reached")
                break
        
        return "changes_requested", issues_found, metadata
    
    def _get_diff(self, repo_path: str, base: str, branch: str) -> str:
        """Get the diff between two branches."""
        try:
            # Fetch latest from both branches
            subprocess.run(["git", "fetch", "origin", base, branch], 
                         cwd=repo_path, capture_output=True)
            
            # Get diff
            result = subprocess.run(
                ["git", "diff", f"origin/{base}...origin/{branch}", "--stat", "--unified=5"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                # Try local diff
                result = subprocess.run(
                    ["git", "diff", f"{base}...{branch}", "--stat", "--unified=5"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True
                )
            
            return result.stdout + result.stderr
            
        except Exception as e:
            self.logger.error(f"Failed to get diff: {e}")
            return ""
    
    def _review_changes(self, changes: str, branch: str, base: str) -> Dict[str, Any]:
        """
        Use OpenCode/Claude to review the changes.
        
        Returns:
            Dict with status (APPROVED/CHANGES_REQUESTED) and feedback
        """
        prompt = self.review_prompt_template.format(
            changes=changes[:15000],  # Limit to 15k chars
            branch=branch,
            base=base
        )
        
        try:
            # Use opencode to do the review
            cmd = [
                self.OPENCODE_PATH,
                "run",
                "--print-logs",
                prompt
            ]
            
            result = subprocess.run(
                cmd,
                cwd=os.getcwd(),  # Run in current directory
                capture_output=True,
                text=True,
                timeout=180
            )
            
            output = result.stdout + result.stderr
            
            # Parse the output for approval/changes status
            if "APPROVED" in output and "CHANGES REQUESTED" not in output:
                return {"status": "APPROVED", "feedback": ""}
            elif "CHANGES REQUESTED" in output:
                # Extract the issues
                return {"status": "CHANGES REQUESTED", "feedback": output}
            else:
                # Default to requesting changes if unclear
                return {"status": "CHANGES_REQUESTED", "feedback": output}
                
        except subprocess.TimeoutExpired:
            self.logger.error("Review timed out")
            return {"status": "ERROR", "feedback": "Review timed out"}
        except Exception as e:
            self.logger.error(f"Review failed: {e}")
            return {"status": "ERROR", "feedback": str(e)}
    
    def _parse_issues(self, feedback: str) -> List[str]:
        """Parse issues from review feedback."""
        issues = []
        
        # Look for numbered list items
        import re
        # Match "1. [Issue]" or "- [Issue]" patterns
        pattern = r'(?:^|\n)\s*(?:\d+[\.\)]\s*|[-*]\s*)([^\n]+)'
        matches = re.findall(pattern, feedback)
        
        for match in matches:
            issue = match.strip()
            # Filter out generic statements
            if issue and len(issue) > 10 and not issue.startswith("###"):
                issues.append(issue)
        
        return issues[:10]  # Limit to top 10 issues
    
    def review_pr(
        self,
        github_client,
        owner: str,
        repo: str,
        pr_number: int
    ) -> Dict[str, Any]:
        """
        Review a GitHub Pull Request.
        
        Uses GitHub's review API to submit review comments.
        """
        self.logger.info(f"Reviewing PR #{pr_number} in {owner}/{repo}")
        
        # Get PR details
        pr = github_client.get_pull_request(pr_number)
        
        # In a full implementation, we would:
        # 1. Get the diff from GitHub
        # 2. Run local review
        # 3. Submit review via GitHub API
        
        return {
            "pr_number": pr_number,
            "status": "reviewed",
            "recommendation": "COMMENT"  # or APPROVE / REQUEST_CHANGES
        }


class ReviewLoop:
    """
    Orchestrates the review loop between coder and reviewer.
    
    Pattern:
    1. Coder makes changes
    2. Reviewer reviews
    3. If issues → Coder fixes → repeat
    4. If approved → merge
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.reviewer = ReviewerAgent(config=config)
        self.logger = get_logger("autodev.review_loop")
        self.max_iterations = self.config.get("review", {}).get("max_iterations", 3)
    
    def run_review_loop(
        self,
        repo_path: str,
        branch: str,
        base: str = "main",
        on_fix_callback=None
    ) -> Dict[str, Any]:
        """
        Run the review loop until approved or max iterations.
        
        Args:
            repo_path: Path to repository
            branch: Branch to review
            base: Base branch
            on_fix_callback: Function to call when fixes are needed
            
        Returns:
            Dict with final status and all issues found
        """
        self.logger.info(f"Starting review loop for {branch}")
        
        all_issues = []
        iterations = 0
        
        while iterations < self.max_iterations:
            iterations += 1
            self.logger.info(f"Review iteration {iterations}/{self.max_iterations}")
            
            # Run review
            status, issues, metadata = self.reviewer.review_branch(
                repo_path, branch, base, max_retries=1
            )
            
            all_issues.extend(issues)
            
            if status == "approved":
                self.logger.info("✅ Review loop complete: APPROVED")
                return {
                    "status": "approved",
                    "iterations": iterations,
                    "issues": all_issues
                }
            
            # If not approved and we have a callback, ask for fixes
            if on_fix_callback and issues:
                self.logger.info(f"Requesting fixes for {len(issues)} issues")
                fixed = on_fix_callback(issues)
                
                if not fixed:
                    self.logger.warning("Fix callback returned False, stopping")
                    break
        
        return {
            "status": "changes_requested",
            "iterations": iterations,
            "issues": all_issues
        }
