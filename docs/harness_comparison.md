# AutoDev vs OpenAI Harness Engineering - Gap Analysis

## What OpenAI Did (Article Summary)

### Core Philosophy
- **Humans steer, agents execute** - Engineers design environments, specify intent, build feedback loops
- **0 lines of manually-written code** - Everything written by Codex
- **~1,500 PRs merged** - 3.5 PRs/engineer/day

---

## Feature-by-Feature Comparison (Updated)

| Feature | OpenAI | AutoDev | Status |
|---------|--------|---------|--------|
| **1. Issue/Task → Code** | | | |
| Prompt → Code | ✅ Full autonomy | ✅ Full autonomy | ✅ Done |
| Test writing | ✅ Agents write tests | ✅ Coder agent does this | ✅ Done |
| PR creation | ✅ Auto-create PR | ✅ PRManager | ✅ Done |
| **Agent-to-agent review** | ✅ Codex reviews Codex | ✅ Reviewer Agent | ✅ DONE |
| **Iterate until approved** | ✅ Loop until passing | ✅ Review → Fix loop | ✅ DONE |
| **CLAUDE.md context** | ✅ AGENTS.md | ✅ Auto-created | ✅ DONE |
| Auto-merge after CI | ✅ Detects CI pass, merges | ❌ Not yet | 🔲 Future |

| **2. Environment & Execution** | | | |
| Worktrees per change | ✅ Per git worktree | ✅ ParallelExecutor | ✅ Done |
| Bootable per worktree | ✅ App runs in each | ❌ Not integrated | 🔲 Future |
| Chrome DevTools Protocol | ✅ UI testing, bug repro | ❌ Not yet | 🔲 Future |

| **3. Observability** | | | |
| Logs accessible to agents | ✅ LogQL | ✅ Activity logger | ✅ Done |
| Metrics accessible to agents | ✅ PromQL | ❌ Not yet | 🔲 Future |
| Traces | ✅ OpenTelemetry | ❌ Not yet | 🔲 Future |
| Live dashboard | ✅ Ephemeral per worktree | ✅ Flask dashboard | ✅ Done |

| **4. Knowledge Management** | | | |
| AGENTS.md as table of contents | ✅ Short (~100 lines) | ✅ CLAUDE.md auto-created | ✅ Done |
| Structured docs/ | ✅ System of record | ✅ docs/ folder | ✅ Done |
| Plans as first-class artifacts | ✅ Versioned plans | ✅ JSON plan | ✅ Done |
| Doc linters | ✅ CI validates docs | ❌ Not yet | 🔲 Future |

| **5. Architecture Enforcement** | | | |
| Layered architecture | ✅ Strict layers | ❌ Not enforced | 🔲 Future |
| Custom linters | ✅ Codex writes lints | ❌ Not yet | 🔲 Future |
| Taste invariants | ✅ Structured logging, naming | ❌ Not yet | 🔲 Future |
| Boundary validation | ✅ Mechanical enforcement | ❌ Not yet | 🔲 Future |

| **6. Autonomy Level** | | | |
| Validate current state | ✅ | ✅ Worktree setup | ✅ Done |
| Reproduce bug | ✅ Video + repro | ❌ Not yet | 🔲 Future |
| Fix + validate fix | ✅ | ✅ Review loop | ✅ Done |
| **Respond to feedback** | ✅ Agent-agent loop | ✅ Review → Fix | ✅ DONE |
| Escalate to human | ✅ When judgment needed | ❌ Not yet | 🔲 Future |

| **7. Maintenance** | | | |
| Garbage collection | ✅ Cleanup agents | ✅ Worktree cleanup | ✅ Done |
| Technical debt tracking | ✅ Quality grades | ❌ Not yet | 🔲 Future |
| Doc-gardening agent | ✅ Auto-fix stale docs | ❌ Not yet | 🔲 Future |

---

## Current AutoDev Status

### ✅ Implemented (Aligned with OpenAI Harness)
1. GitHub issue fetching and parsing (from upstream repos)
2. **CLAUDE.md auto-creation** with project context ⭐
3. Task decomposition (issue → features → subtasks)
4. **Parallel Claude Code agents** with worktrees
5. **Strict Review Agent** before PR ⭐
6. **Research Agent** integration for fixes ⭐
7. **Iterate until approved** loop ⭐
8. Worktree management
9. Activity logger with full observability
10. Dashboard visualization
11. PR creation in user's fork
12. Shared memory context for parallel agents
13. MiniMax-M2.5-highspeed model

### 🔲 Not Yet Implemented (Priority Order)

#### High Priority
1. ~~**Agent-to-agent review**~~ ✅ DONE!
2. ~~**Iterate until approved**~~ ✅ DONE!
3. ~~**CLAUDE.md context**~~ ✅ DONE!
4. **Auto-merge after CI** - Wait for CI → merge

#### Medium Priority
5. **Chrome DevTools integration** - UI bug reproduction
6. **PromQL/LogQL access** - Give agents metric query ability
7. **Architecture linters** - Enforce layered structure
8. **Taste invariants** - Structured logging rules

#### Lower Priority
9. **Garbage collection agent** - Auto-cleanup
10. **Doc-gardening agent** - Fix stale docs
11. **Escalation logic** - Know when to ask humans

---

## OpenAI Harness Alignment Summary

| Principle | OpenAI | AutoDev |
|-----------|--------|---------|
| 0 human intervention | ✅ | ✅ (target) |
| Agent-to-agent review | ✅ | ✅ |
| Parallel workstreams | ✅ | ✅ |
| Research on-demand | ✅ | ✅ |
| Iterate until approved | ✅ | ✅ |
| Worktree isolation | ✅ | ✅ |
| CLAUDE.md context | ✅ | ✅ |
| Observability | ✅ | ✅ |
| Auto-merge | ✅ | 🔲 |

---

## Next Steps

See [README.md](../README.md) for updated roadmap.

*Updated: 2026-03-01*
