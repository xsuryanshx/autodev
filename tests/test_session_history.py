"""Tests for SessionHistory."""
import pytest
import sys
import json
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.session_history import SessionHistory


class TestSessionHistory:
    """Test SessionHistory class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp)
    
    @pytest.fixture
    def session(self, temp_dir):
        """Create SessionHistory instance."""
        return SessionHistory(session_dir=temp_dir)
    
    def test_init(self, session):
        """Test initialization."""
        assert session.session_dir is not None
    
    def test_init_session(self, session):
        """Test initializing a session."""
        session.init_session(issue="Test Issue #1", total_subtasks=5)
        assert session.state is not None
        assert session.state["issue"] == "Test Issue #1"
