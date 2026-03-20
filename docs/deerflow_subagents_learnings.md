# DeerFlow vs AutoDev: Architecture Mapping

## DeerFlow Model

- **Lead agent** — main orchestrator, coordinates work
- **task() tool** — spawns subagents
- **Background concurrent execution** — thread pool
- **Sandboxed tools** — read_file, write_file, bash, etc.
- **Per-thread workspace** — isolation per task
- **Max 3 subagents per turn, 15-min timeout**

## AutoDev New Architecture (Parallel Subagent Model)

| DeerFlow Component | AutoDev Equivalent |
|--------------------|-------------------|
| Lead agent | `/autodev` command (Claude Code) |
| task() tool | `SubagentExecutor.submit_and_wait()` |
| ThreadPoolExecutor | `concurrent.futures.ThreadPoolExecutor` |
| Sandboxed tools | `SandboxedTools` class |
| Per-thread context | `TaskContext` + contextvars |
| Max 3 per turn | `max_parallelism=3` |
| 15-min timeout | `timeout_per_task=900` |
| Result aggregation | Lead agent collects `AgentResult[]` |

## Key Principles

1. **Lead-agent driven**: The main Claude Code session orchestrates, subagents do focused work
2. **Subagent delegated**: Tasks are narrow and skill-specific (coder, researcher)
3. **Concurrently executed**: ThreadPoolExecutor handles parallelism
4. **Sandbox isolated**: Each subagent workspace is restricted to its task directory
5. **Tool mediated**: Subagents use sandboxed tools, not full CLI access
