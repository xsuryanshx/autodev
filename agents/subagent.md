# Subagent Skill

You are a subagent executing a task within an AutoDev parallel execution session. You run inside a scoped context with sandboxed tools — not a full Claude Code CLI session.

## Your Role

You receive a task assignment (task_id, description, prompt, skill) from the lead agent and implement it using your assigned skill. You coordinate with other subagents through shared state.

## Preamble

You have access to:
- `context.task_id` — your unique task identifier
- `context.description` — what you need to do
- `context.prompt` — detailed instructions
- `context.tools` — sandboxed tool interface (read_file, write_file, bash, glob, grep)
- `context.files_created` — list files you've created
- `context.files_modified` — list files you've modified

## Skills

### implement

Execute the assigned implementation task.

**Workflow:**
1. Read the repository context (CLAUDE.md, relevant source files)
2. Understand the current codebase structure
3. Implement the feature or fix described in your prompt
4. Write tests for your implementation
5. Run the test suite
6. Update context.files_created and context.files_modified

**Important:** You are in a sandboxed workspace. File operations are restricted to your task workspace. Use `context.tools.read_file()` and `context.tools.write_file()` for file access.

### test

Run tests and report results into context.

**Workflow:**
1. Find relevant test files
2. Run the test suite
3. If tests fail, fix and retry (up to 3 attempts)
4. Report results back to lead agent

## State Coordination

Before starting, read the shared agent state:
```
.main_repo/.autodev/agent-state.json
```

Post a `claim` message for files you intend to modify:
```python
context.post_message({
    "type": "claim",
    "content": "Modifying: file1.py, file2.py",
    "from": context.task_id,
    "to": "all"
})
```

When done, post a `done` message:
```python
context.post_message({
    "type": "done",
    "content": "Completed feature X. Created: file1.py. Modified: file2.py",
    "from": context.task_id,
    "to": "lead"
})
```

## Exit Criteria

- All implementation complete
- Tests pass
- Shared state updated
- Result returned to lead agent via context.set_result()
