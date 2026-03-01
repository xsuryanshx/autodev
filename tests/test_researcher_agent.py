"""Tests for ResearcherAgent."""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.researcher.agent import ResearcherAgent


class TestResearcherAgentInit:
    """Test ResearcherAgent initialization."""
    
    def test_init(self):
        """Test initialization."""
        agent = ResearcherAgent()
        
        assert agent.config == {}
        assert agent.tavily_api_key is not None
    
    def test_init_with_config(self):
        """Test initialization with config."""
        config = {"timeout": 60}
        agent = ResearcherAgent(config=config)
        
        assert agent.config == config


class TestResearcherAgent:
    """Test ResearcherAgent methods."""
    
    @pytest.fixture
    def agent(self):
        """Create ResearcherAgent instance."""
        return ResearcherAgent()
    
    def test_research_error(self, agent):
        """Test research_error method."""
        result = agent.research_error("TypeError: undefined is not an object")
        
        assert "findings" in result
        assert "recommended_fix" in result
        assert "confidence" in result
    
    def test_build_search_query(self, agent):
        """Test query building."""
        query = agent._build_search_query("TypeError: Cannot read property 'foo' of undefined", None)
        
        assert "TypeError" in query
        assert "Cannot read" in query
    
    def test_build_search_query_with_context(self, agent):
        """Test query building with context."""
        context = {"language": "Python", "framework": "Django"}
        query = agent._build_search_query("ImportError", context)
        
        assert "ImportError" in query
        assert "Python" in query
    
    def test_analyze_results(self, agent):
        """Test analyzing search results."""
        results = [
            {"title": "Fix for TypeError", "snippet": "Solution here", "url": "https://example.com/1", "relevance": 0.9},
            {"title": "Other issue", "snippet": "Other solution", "url": "https://example.com/2", "relevance": 0.3}
        ]
        
        findings = agent._analyze_results(results)
        
        assert len(findings) == 2
        assert findings[0]["relevance"] >= findings[1]["relevance"]
    
    def test_generate_fix(self, agent):
        """Test generating fix recommendation."""
        findings = [
            {"title": "Fix", "url": "https://example.com", "snippet": "Do this"}
        ]
        
        fix = agent._generate_fix(findings, "Original error")
        
        assert "Fix" in fix
        assert "https://example.com" in fix
    
    def test_generate_fix_no_findings(self, agent):
        """Test generating fix with no findings."""
        fix = agent._generate_fix([], "Error")
        
        assert "No solutions found" in fix
    
    def test_calculate_confidence(self, agent):
        """Test confidence calculation."""
        findings = [
            {"relevance": 0.9},
            {"relevance": 0.8},
            {"relevance": 0.7}
        ]
        
        confidence = agent._calculate_confidence(findings)
        
        assert 0.0 <= confidence <= 1.0
    
    def test_deep_research(self, agent):
        """Test deep research."""
        result = agent.deep_research("React hooks", max_results=5)
        
        assert "topic" in result
        assert "findings" in result
        assert result["topic"] == "React hooks"
