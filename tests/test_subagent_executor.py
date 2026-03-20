import pytest
import tempfile
import time
from unittest.mock import MagicMock, patch
from core.subagent_executor import SubagentExecutor, SubagentTask, AgentResult

class TestSubagentExecutorBasics:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()

    def test_executor_initializes(self):
        executor = SubagentExecutor(
            workspace=self.tempdir,
            max_parallelism=2,
            timeout_per_task=300,
        )
        assert executor.max_parallelism == 2
        assert executor.timeout_per_task == 300

    def test_submit_single_task(self):
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=1)
        task = SubagentTask(
            task_id="task-1",
            description="Simple task",
            prompt="Return immediately",
            skill="coder",
        )

        def simple_handler(ctx):
            return {"status": "completed", "output": "done"}

        with patch.object(executor, "_get_handler_for_skill", return_value=simple_handler):
            result = executor.submit_and_wait([task])

        assert len(result) == 1
        assert result[0].task_id == "task-1"
        assert result[0].status == "completed"

    def test_submit_multiple_tasks_concurrent(self):
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=3)
        tasks = [
            SubagentTask(task_id=f"task-{i}", description=f"Task {i}", prompt="", skill="coder")
            for i in range(3)
        ]

        # Track call count to return different handlers
        call_count = [0]
        handlers = []

        def make_handler(task_id):
            def handler(ctx):
                time.sleep(0.1)
                return {"status": "completed", "task_id": task_id}
            return handler

        # Create handlers upfront
        for i in range(3):
            handlers.append(make_handler(f"task-{i}"))

        def handler_provider(skill):
            idx = call_count[0]
            call_count[0] += 1
            return handlers[idx]

        start = time.time()
        with patch.object(executor, "_get_handler_for_skill", side_effect=handler_provider):
            result = executor.submit_and_wait(tasks)

        elapsed = time.time() - start
        assert len(result) == 3
        assert all(r.status == "completed" for r in result)
        # With max_parallelism=3 and 3 tasks sleeping 0.1s each, should take ~0.1s not ~0.3s
        assert elapsed < 0.25, f"Took {elapsed}s, expected < 0.25s (tasks should run concurrently)"


class TestConcurrencyLimits:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()

    def test_max_parallelism_respected(self):
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=2)
        assert executor.max_parallelism == 2
        assert executor._semaphore._value == 2

    def test_task_timeout_applied(self):
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=1, timeout_per_task=5)
        task = SubagentTask(
            task_id="slow-task",
            description="Slow task",
            prompt="",
            skill="coder",
            timeout_seconds=1,
        )

        def slow_handler(ctx):
            time.sleep(2)
            return {"status": "completed"}

        with patch.object(executor, "_get_handler_for_skill", return_value=slow_handler):
            result = executor.submit_and_wait([task])

        assert result[0].status == "timeout"
        assert "timeout" in result[0].error.lower()