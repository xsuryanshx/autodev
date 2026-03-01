"""Tests for GitHubClient."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.github_client import GitHubClient


class TestGitHubClientInit:
    """Test GitHubClient initialization."""
    
    def test_init_with_token(self):
        """Test initialization with token."""
        client = GitHubClient(token="test_token", owner="owner", repo="repo")
        assert client.token == "test_token"
        assert client.owner == "owner"
        assert client.repo == "repo"
        assert "Authorization" in client.headers
    
    def test_init_without_token(self, monkeypatch):
        """Test initialization without token (from env)."""
        monkeypatch.setenv("GITHUB_TOKEN", "env_token")
        client = GitHubClient(owner="owner", repo="repo")
        assert client.token == "env_token"
    
    def test_init_missing_owner_repo(self):
        """Test that missing owner/repo raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            GitHubClient(token="token")
        assert "owner and repo are required" in str(exc_info.value)
    
    def test_set_repo(self):
        """Test set_repo method."""
        client = GitHubClient(token="token", owner="owner", repo="repo")
        client.set_repo("new_owner", "new_repo")
        assert client.owner == "new_owner"
        assert client.repo == "new_repo"


class TestGitHubClientMethods:
    """Test GitHubClient methods (mocked)."""
    
    @pytest.fixture
    def client(self):
        """Create client with mock."""
        return GitHubClient(token="test_token", owner="owner", repo="repo")
    
    def test_base_url(self, client):
        """Test base URL is correct."""
        assert client.base_url == "https://api.github.com"
    
    def test_headers(self, client):
        """Test headers include accept and auth."""
        assert "Accept" in client.headers
        assert "Authorization" in client.headers
        assert client.headers["Accept"] == "application/vnd.github.v3+json"
