"""Tests for ReviewerAgent."""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.reviewer.agent import ReviewerAgent, ReviewLoop


class TestReviewerAgentInit:
    """Test ReviewerAgent initialization."""
    
    def test_init(self):
        """Test initialization."""
        agent = ReviewerAgent(agent_id="reviewer_1")
        
        assert agent.agent_id == "reviewer_1"
        assert agent.config == {}
    
    def test_init_with_config(self):
        """Test initialization with config."""
        config = {"max_retries": 5}
        agent = ReviewerAgent(config=config)
        
        assert agent.config == config


class TestReviewerAgent:
    """Test ReviewerAgent methods."""
    
    @pytest.fixture
    def agent(self):
        """Create ReviewerAgent instance."""
        return ReviewerAgent()
    
    def test_initialize(self, agent):
        """Test initialize method."""
        mock_github = Mock()
        agent.initialize(mock_github)
        
        assert agent.github_client == mock_github
    
    def test_review_prompt_template(self, agent):
        """Test review prompt template is set."""
        assert agent.review_prompt_template is not None
        assert "CHANGES REQUESTED" in agent.review_prompt_template
        assert "APPROVED" in agent.review_prompt_template
    
    def test_parse_issues(self, agent):
        """Test parsing issues from feedback."""
        feedback = """
        CHANGES REQUESTED
        
        1. Fix the TypeError on line 42
        2. Add error handling
        3. Missing test coverage
        """
        
        issues = agent._parse_issues(feedback)
        
        assert len(issues) > 0
        assert any("TypeError" in issue for issue in issues)
    
    def test_parse_issues_empty(self, agent):
        """Test parsing empty feedback."""
        issues = agent._parse_issues("")
        
        assert len(issues) == 0


class TestReviewLoop:
    """Test ReviewLoop class."""
    
    def test_init(self):
        """Test ReviewLoop initialization."""
        loop = ReviewLoop()
        
        assert loop.max_iterations == 3
        assert hasattr(loop, 'reviewer')
    
    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = {"review": {"max_iterations": 5}}
        loop = ReviewLoop(config=config)
        
        assert loop.max_iterations == 5
