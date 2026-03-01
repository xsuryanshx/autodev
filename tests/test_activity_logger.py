"""Tests for ActivityLogger."""
import pytest
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.activity_logger import ActivityLogger


class TestActivityLogger:
    """Test ActivityLogger class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp)
    
    @pytest.fixture
    def logger(self, temp_dir):
        """Create ActivityLogger instance."""
        return ActivityLogger(repo="test/repo", log_dir=temp_dir)
    
    def test_init(self, logger):
        """Test initialization."""
        assert logger.session_id is not None
        assert logger.repo == "test/repo"
