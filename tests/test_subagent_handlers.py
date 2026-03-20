import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch
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
        ctx = TaskContext(
            task_id="test-1",
            description="Test task",
            prompt="Implement auth",
            context={},
        )

        with patch.object(handler, '_execute_impl', return_value={"status": "completed"}):
            result = handler.execute(ctx)

        assert isinstance(result, dict)
        assert result["status"] == "completed"

    def test_coder_handler_stores_result_on_context(self):
        from agents.subagent_handlers import CoderHandler
        handler = CoderHandler()
        ctx = TaskContext(
            task_id="test-2",
            description="Test task 2",
            prompt="Implement feature",
            context={},
        )

        expected_result = {"status": "completed", "message": "done"}
        with patch.object(handler, '_execute_impl', return_value=expected_result):
            handler.execute(ctx)

        assert ctx.result == expected_result

    def test_coder_handler_catches_exception(self):
        from agents.subagent_handlers import CoderHandler
        handler = CoderHandler()
        ctx = TaskContext(
            task_id="test-3",
            description="Test task 3",
            prompt="Implement something",
            context={},
        )

        with patch.object(handler, '_execute_impl', side_effect=RuntimeError("test error")):
            result = handler.execute(ctx)

        assert result["status"] == "failed"
        assert "test error" in result["error"]
        assert ctx.error is not None

    def test_coder_handler_passes_prompt_to_impl(self):
        from agents.subagent_handlers import CoderHandler
        handler = CoderHandler()
        ctx = TaskContext(
            task_id="test-4",
            description="Test prompt pass-through",
            prompt="Implement JWT middleware for auth endpoints",
            context={"repo_path": "/tmp/repo"},
        )

        # Use real stub _execute_impl
        result = handler.execute(ctx)
        assert result["status"] == "completed"
        assert "JWT middleware" in result["prompt_summary"]


class TestResearcherHandler:
    def test_researcher_handler_implements_researcher_skill(self):
        from agents.subagent_handlers import ResearcherHandler
        handler = ResearcherHandler()
        assert hasattr(handler, 'execute')
        assert callable(handler.execute)

    def test_researcher_handler_returns_result_dict(self):
        from agents.subagent_handlers import ResearcherHandler
        handler = ResearcherHandler()
        ctx = TaskContext(
            task_id="research-1",
            description="Research task",
            prompt="Research auth best practices",
            context={},
        )

        with patch.object(handler, '_research', return_value={"status": "completed", "findings": []}):
            result = handler.execute(ctx)

        assert isinstance(result, dict)
        assert result["status"] == "completed"

    def test_researcher_handler_stores_result_on_context(self):
        from agents.subagent_handlers import ResearcherHandler
        handler = ResearcherHandler()
        ctx = TaskContext(
            task_id="research-2",
            description="Research task 2",
            prompt="Find error solutions",
            context={},
        )

        expected_result = {"status": "completed", "findings": [{"title": "Test"}]}
        with patch.object(handler, '_research', return_value=expected_result):
            handler.execute(ctx)

        assert ctx.result == expected_result

    def test_researcher_handler_catches_exception(self):
        from agents.subagent_handlers import ResearcherHandler
        handler = ResearcherHandler()
        ctx = TaskContext(
            task_id="research-3",
            description="Research task 3",
            prompt="Find something",
            context={},
        )

        with patch.object(handler, '_research', side_effect=RuntimeError("research error")):
            result = handler.execute(ctx)

        assert result["status"] == "failed"
        assert "research error" in result["error"]
        assert ctx.error is not None
