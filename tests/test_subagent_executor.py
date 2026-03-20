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

        executor.register_handler("coder", simple_handler)
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

        def handler(ctx):
            time.sleep(0.1)
            return {"status": "completed", "task_id": ctx.task_id}

        executor.register_handler("coder", handler)

        start = time.time()
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

    def test_task_context_gets_prompt_and_context(self):
        """Verify that TaskContext receives prompt and context from SubagentTask."""
        executor = SubagentExecutor(workspace=self.tempdir, max_parallelism=1)
        task = SubagentTask(
            task_id="ctx-task",
            description="Context test",
            prompt="Do something specific",
            skill="coder",
            context={"repo_path": "/tmp/repo"},
        )

        captured = {}
        def capturing_handler(ctx):
            captured["prompt"] = ctx.prompt
            captured["context"] = ctx.context
            return {"status": "completed"}

        executor.register_handler("coder", capturing_handler)
        executor.submit_and_wait([task])

        assert captured["prompt"] == "Do something specific"
        assert captured["context"] == {"repo_path": "/tmp/repo"}
