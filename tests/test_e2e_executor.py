"""End-to-end test: real executor, real file I/O, real sandboxed tools.

Run manually:
    python -m pytest tests/test_e2e_executor.py -v -s
"""
import tempfile
import json
from pathlib import Path
from core.subagent_executor import SubagentExecutor, SubagentTask
from core.task_context import TaskContext


def coder_handler(ctx: TaskContext):
    """Simulates a real coder: reads a file, writes implementation + test."""
    # Read the "spec" file placed in the workspace
    spec = ctx.tools.read_file("spec.json")
    if spec["status"] != "success":
        raise RuntimeError(f"Could not read spec: {spec.get('message')}")

    spec_data = json.loads(spec["content"])
    module_name = spec_data["module"]
    function_name = spec_data["function"]

    # Write implementation
    impl_code = f'def {function_name}(x):\n    return x * 2\n'
    ctx.tools.write_file(f"{module_name}.py", impl_code)
    ctx.add_file_created(f"{module_name}.py")

    # Write test
    test_code = (
        f'from {module_name} import {function_name}\n'
        f'def test_{function_name}():\n'
        f'    assert {function_name}(5) == 10\n'
    )
    ctx.tools.write_file(f"test_{module_name}.py", test_code)
    ctx.add_file_created(f"test_{module_name}.py")

    # Run the test via bash
    run_result = ctx.tools.bash(f"python -m pytest test_{module_name}.py -v")
    tests_passed = run_result["status"] == "success"

    return {
        "status": "completed" if tests_passed else "failed",
        "tests_passed": tests_passed,
        "test_output": run_result.get("stdout", ""),
    }


class TestE2EExecutor:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()

    def test_two_coders_produce_independent_modules(self):
        executor = SubagentExecutor(
            workspace=self.tempdir,
            max_parallelism=2,
            timeout_per_task=30,
        )
        executor.register_handler("coder", coder_handler)

        # Place spec files in each task workspace ahead of time
        for task_id, module, function in [
            ("feat-1", "math_utils", "double"),
            ("feat-2", "string_utils", "repeat"),
        ]:
            ws = Path(self.tempdir) / f"task_{task_id}"
            ws.mkdir(parents=True, exist_ok=True)
            spec = {"module": module, "function": function}
            (ws / "spec.json").write_text(json.dumps(spec))

        tasks = [
            SubagentTask(
                task_id="feat-1",
                description="Implement math_utils.double",
                prompt="Create double function",
                skill="coder",
            ),
            SubagentTask(
                task_id="feat-2",
                description="Implement string_utils.repeat",
                prompt="Create repeat function",
                skill="coder",
            ),
        ]

        results = executor.submit_and_wait(tasks)
        executor.shutdown()

        # Both should complete
        assert len(results) == 2
        for r in results:
            assert r.status == "completed", f"{r.task_id} failed: {r.error}"
            assert r.output["tests_passed"] is True
            assert len(r.files_created) == 2

        # Verify files actually exist on disk
        assert (Path(self.tempdir) / "task_feat-1" / "math_utils.py").exists()
        assert (Path(self.tempdir) / "task_feat-2" / "string_utils.py").exists()

    def test_coder_with_missing_spec_fails_gracefully(self):
        executor = SubagentExecutor(
            workspace=self.tempdir,
            max_parallelism=1,
            timeout_per_task=10,
        )
        executor.register_handler("coder", coder_handler)

        # Don't create the spec file — handler should fail
        task = SubagentTask(
            task_id="no-spec",
            description="Task with no spec",
            prompt="Should fail",
            skill="coder",
        )
        results = executor.submit_and_wait([task])
        executor.shutdown()

        assert results[0].status == "failed"
        assert "spec" in results[0].error.lower() or "not found" in results[0].error.lower()
