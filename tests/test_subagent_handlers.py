import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.task_context import TaskContext


class TestCoderHandler:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()

    def test_coder_handler_implements_coder_skill(self):
        from agents.subagent_handlers import CoderHandler
        handler = CoderHandler()
        assert hasattr(handler, 'execute')
        assert callable(handler.execute)

    def test_coder_handler_returns_result_dict(self):
        from agents.subagent_handlers import CoderHandler
        handler = CoderHandler()
        mock_context = MagicMock()
        mock_context.task_id = "test-1"
        mock_context.description = "Test task"
        mock_context.tools.read_file.return_value = {"status": "success", "content": ""}
        mock_context.files_created = []
        mock_context.files_modified = []
        mock_context.context = {}

        with patch.object(handler, '_execute_impl', return_value={"status": "completed"}):
            result = handler.execute(mock_context)

        assert isinstance(result, dict)
        assert result["status"] == "completed"

    def test_coder_handler_stores_result_on_context(self):
        from agents.subagent_handlers import CoderHandler
        handler = CoderHandler()
        mock_context = MagicMock()
        mock_context.task_id = "test-2"
        mock_context.description = "Test task 2"
        mock_context.files_created = []
        mock_context.files_modified = []
        mock_context.context = {}

        expected_result = {"status": "completed", "message": "done"}
        with patch.object(handler, '_execute_impl', return_value=expected_result):
            handler.execute(mock_context)

        mock_context.set_result.assert_called_once_with(expected_result)

    def test_coder_handler_catches_exception(self):
        from agents.subagent_handlers import CoderHandler
        handler = CoderHandler()
        mock_context = MagicMock()
        mock_context.task_id = "test-3"
        mock_context.description = "Test task 3"
        mock_context.files_created = []
        mock_context.files_modified = []
        mock_context.context = {}

        with patch.object(handler, '_execute_impl', side_effect=RuntimeError("test error")):
            result = handler.execute(mock_context)

        assert result["status"] == "failed"
        assert "test error" in result["error"]
        mock_context.set_error.assert_called_once()


class TestResearcherHandler:
    def test_researcher_handler_implements_researcher_skill(self):
        from agents.subagent_handlers import ResearcherHandler
        handler = ResearcherHandler()
        assert hasattr(handler, 'execute')
        assert callable(handler.execute)

    def test_researcher_handler_returns_result_dict(self):
        from agents.subagent_handlers import ResearcherHandler
        handler = ResearcherHandler()
        mock_context = MagicMock()
        mock_context.task_id = "research-1"
        mock_context.description = "Research task"
        mock_context.files_created = []
        mock_context.files_modified = []
        mock_context.context = {}

        with patch.object(handler, '_research', return_value={"status": "completed", "findings": []}):
            result = handler.execute(mock_context)

        assert isinstance(result, dict)
        assert result["status"] == "completed"

    def test_researcher_handler_stores_result_on_context(self):
        from agents.subagent_handlers import ResearcherHandler
        handler = ResearcherHandler()
        mock_context = MagicMock()
        mock_context.task_id = "research-2"
        mock_context.description = "Research task 2"
        mock_context.files_created = []
        mock_context.files_modified = []
        mock_context.context = {}

        expected_result = {"status": "completed", "findings": [{"title": "Test", "url": "http://test.com"}]}
        with patch.object(handler, '_research', return_value=expected_result):
            handler.execute(mock_context)

        mock_context.set_result.assert_called_once_with(expected_result)

    def test_researcher_handler_catches_exception(self):
        from agents.subagent_handlers import ResearcherHandler
        handler = ResearcherHandler()
        mock_context = MagicMock()
        mock_context.task_id = "research-3"
        mock_context.description = "Research task 3"
        mock_context.files_created = []
        mock_context.files_modified = []
        mock_context.context = {}

        with patch.object(handler, '_research', side_effect=RuntimeError("research error")):
            result = handler.execute(mock_context)

        assert result["status"] == "failed"
        assert "research error" in result["error"]
        mock_context.set_error.assert_called_once()