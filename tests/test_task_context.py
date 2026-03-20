import pytest
from core.task_context import TaskContext, task_scope

class TestTaskContext:
    def test_task_has_unique_id(self):
        ctx1 = TaskContext(task_id="task-1", description="Do thing A")
        ctx2 = TaskContext(task_id="task-2", description="Do thing B")
        assert ctx1.task_id != ctx2.task_id
        assert ctx1.task_id == "task-1"

    def test_task_stores_files_created(self):
        ctx = TaskContext(task_id="task-1", description="Write files")
        ctx.add_file_created("src/auth.py")
        ctx.add_file_created("tests/test_auth.py")
        assert len(ctx.files_created) == 2
        assert "src/auth.py" in ctx.files_created

    def test_task_stores_files_modified(self):
        ctx = TaskContext(task_id="task-1", description="Modify config")
        ctx.add_file_modified("config.py")
        assert "config.py" in ctx.files_modified

    def test_task_has_status(self):
        ctx = TaskContext(task_id="task-1", description="Do work")
        assert ctx.status == "pending"
        ctx.set_status("running")
        assert ctx.status == "running"
        ctx.set_status("completed")
        assert ctx.status == "completed"

    def test_task_has_timeout(self):
        ctx = TaskContext(task_id="task-1", description="Do work", timeout_seconds=300)
        assert ctx.timeout_seconds == 300

    def test_task_summary(self):
        ctx = TaskContext(task_id="task-1", description="Fix auth bug")
        ctx.add_file_created("src/auth.py")
        summary = ctx.get_summary()
        assert "task-1" in summary
        assert "auth.py" in summary


class TestTaskScope:
    def test_task_scope_sets_current_context(self):
        ctx = TaskContext(task_id="test-1", description="Test")
        with task_scope(ctx):
            from core.task_context import get_current_task_context
            assert get_current_task_context() is ctx
        # After exiting scope, no current context
        try:
            get_current_task_context()
            assert False, "Should raise - no current context"
        except RuntimeError:
            pass

    def test_nested_task_scopes_raise(self):
        ctx1 = TaskContext(task_id="outer", description="Outer")
        ctx2 = TaskContext(task_id="inner", description="Inner")
        with task_scope(ctx1):
            with pytest.raises(RuntimeError, match="Nested task_scope"):
                with task_scope(ctx2):
                    pass