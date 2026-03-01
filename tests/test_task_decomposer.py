"""Tests for TaskDecomposer."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.task_decomposer import TaskDecomposer


class TestTaskDecomposer:
    """Test TaskDecomposer class."""
    
    @pytest.fixture
    def decomposer(self):
        """Create TaskDecomposer instance."""
        return TaskDecomposer()
    
    def test_init(self, decomposer):
        """Test initialization."""
        assert decomposer is not None
    
    def test_decompose_issue(self, decomposer):
        """Test decomposing an Issue into features and subtasks."""
        issue = {"title": "Test", "body": "Body"}
        plan = decomposer.decompose_issue(issue)
        assert "features" in plan
        assert "metadata" in plan


class TestTaskDecomposerEdgeCases:
    """Test edge cases."""
    
    @pytest.fixture
    def decomposer(self):
        """Create TaskDecomposer instance."""
        return TaskDecomposer()
    
    def test_empty_issue(self, decomposer):
        """Test with empty issue."""
        issue = {"title": "", "body": ""}
        plan = decomposer.decompose_issue(issue)
        assert "features" in plan
    
    def test_issue_with_special_chars(self, decomposer):
        """Test issue with special characters."""
        issue = {
            "title": "Fix #123 bug in API",
            "body": "Use pytest.raises() for error handling"
        }
        plan = decomposer.decompose_issue(issue)
        assert plan is not None
