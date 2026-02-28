"""GitHub API client for AutoDev."""
import os
import base64
from typing import Optional
import requests


class GitHubClient:
    """Handles GitHub API interactions."""
    
    def __init__(self, token: Optional[str] = None, owner: Optional[str] = None, repo: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.owner = owner
        self.repo = repo
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
    
    def set_repo(self, owner: str, repo: str):
        """Set the repository to work with."""
        self.owner = owner
        self.repo = repo
    
    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an authenticated request to GitHub API."""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("headers", self.headers)
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}
    
    def get_issue(self, issue_number: int) -> dict:
        """Fetch an issue by number."""
        return self._request(
            "GET", 
            f"/repos/{self.owner}/{self.repo}/issues/{issue_number}"
        )
    
    def get_issue_comments(self, issue_number: int) -> list:
        """Fetch all comments on an issue."""
        return self._request(
            "GET",
            f"/repos/{self.owner}/{self.repo}/issues/{issue_number}/comments"
        )
    
    def get_file_content(self, path: str, ref: str = "main") -> str:
        """Get file content from repository."""
        content = self._request(
            "GET",
            f"/repos/{self.owner}/{self.repo}/contents/{path}",
            params={"ref": ref}
        )
        if content.get("encoding") == "base64":
            return base64.b64decode(content["content"]).decode("utf-8")
        return content.get("content", "")
    
    def list_files(self, path: str = "", ref: str = "main") -> list:
        """List files in a directory."""
        try:
            return self._request(
                "GET",
                f"/repos/{self.owner}/{self.repo}/contents/{path}",
                params={"ref": ref}
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return []
            raise
    
    def create_branch(self, branch_name: str, base_sha: str) -> dict:
        """Create a new branch."""
        return self._request(
            "POST",
            f"/repos/{self.owner}/{self.repo}/git/refs",
            json={
                "ref": f"refs/heads/{branch_name}",
                "sha": base_sha
            }
        )
    
    def get_default_branch_sha(self) -> str:
        """Get the SHA of the default branch."""
        repo = self._request("GET", f"/repos/{self.owner}/{self.repo}")
        return repo["default_branch"]
    
    def create_or_update_file(
        self, 
        path: str, 
        content: str, 
        message: str, 
        branch: str, 
        sha: Optional[str] = None
    ) -> dict:
        """Create or update a file in the repository."""
        import urllib.parse
        
        encoded_path = urllib.parse.quote(path, safe="/")
        data = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch
        }
        if sha:
            data["sha"] = sha
        
        return self._request(
            "PUT",
            f"/repos/{self.owner}/{self.repo}/contents/{encoded_path}",
            json=data
        )
    
    def create_pull_request(
        self,
        title: str,
        body: str,
        head: str,
        base: str = "main"
    ) -> dict:
        """Create a pull request."""
        return self._request(
            "POST",
            f"/repos/{self.owner}/{self.repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base
            }
        )
    
    def list_pulls(self, state: str = "open") -> list:
        """List pull requests."""
        return self._request(
            "GET",
            f"/repos/{self.owner}/{self.repo}/pulls",
            params={"state": state}
        )
    
    def get_pull_request(self, pull_number: int) -> dict:
        """Get a specific pull request."""
        return self._request(
            "GET",
            f"/repos/{self.owner}/{self.repo}/pulls/{pull_number}"
        )
    
    def merge_pr(self, pull_number: int, commit_message: str = "") -> dict:
        """Merge a pull request."""
        return self._request(
            "PUT",
            f"/repos/{self.owner}/{self.repo}/pulls/{pull_number}/merge",
            json={"commit_message": commit_message}
        )
    
    def add_pr_reviewers(self, pull_number: int, reviewers: list) -> dict:
        """Add reviewers to a pull request."""
        return self._request(
            "POST",
            f"/repos/{self.owner}/{self.repo}/pulls/{pull_number}/requested_reviewers",
            json={"reviewers": reviewers}
        )
