import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.subagent_executor import SubagentExecutor, SubagentTask


class TestParallelSubagentIntegration:
    """Integration test for the full parallel subagent pipeline."""

    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()

    def test_multiple_tasks_run_concurrently(self):
        """Verify 3 tasks complete in ~parallel time, not sequential."""
        executor = SubagentExecutor(
            workspace=self.tempdir,
            max_parallelism=3,
            timeout_per_task=60,
        )

        def slow_handler(ctx):
            tid = ctx.task_id
            time.sleep(0.2)
            return {"status": "completed", "task_id": tid}

        executor.register_handler("coder", slow_handler)

        tasks = [
            SubagentTask(task_id=f"task-{i}", description=f"Task {i}", prompt="", skill="coder")
            for i in range(3)
        ]

        start = time.time()
        results = executor.submit_and_wait(tasks)
        elapsed = time.time() - start

        assert len(results) == 3
        assert all(r.status == "completed" for r in results)
        # Should take ~0.2s (parallel), not ~0.6s (sequential)
        assert elapsed < 0.4, f"Took {elapsed:.2f}s — tasks may not be running concurrently"

    def test_failed_task_returns_error(self):
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=1)

        def failing_handler(ctx):
            raise ValueError("Intentional failure")

        executor.register_handler("coder", failing_handler)

        task = SubagentTask(task_id="fail-1", description="Failing task", prompt="", skill="coder")
        results = executor.submit_and_wait([task])

        assert results[0].status == "failed"
        assert "ValueError" in results[0].error

    def test_unknown_skill_returns_error(self):
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=1)
        task = SubagentTask(task_id="unknown-1", description="Unknown skill", prompt="", skill="nonexistent")
        results = executor.submit_and_wait([task])

        assert results[0].status == "failed"
        assert "No handler" in results[0].error
