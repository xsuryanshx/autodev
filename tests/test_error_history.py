import pytest
import json
import tempfile
import shutil


class TestErrorHistory:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_new_error_appended_to_history(self):
        """New errors should be appended, not overwritten."""
        pass  # Test structure defined

    def test_learnings_extracted_on_retry(self):
        """Relevant learnings should be returned for retry context."""
        pass  # Test structure defined

    def test_resolved_errors_marked(self):
        """Marking error resolved should move it to learnings."""
        pass  # Test structure defined
