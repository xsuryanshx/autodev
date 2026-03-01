# AutoDev vs OpenAI Harness Engineering - Gap Analysis

## What OpenAI Did (Article Summary)

### Core Philosophy
- **Humans steer, agents execute** - Engineers design environments, specify intent, build feedback loops
- **0 lines of manually-written code** - Everything written by Codex
- **~1,500 PRs merged** - 3.5 PRs/engineer/day

---

## Feature-by-Feature Comparison

| Feature | OpenAI | AutoDev | Status |
|---------|--------|---------|--------|
| **1. Issue/Task → Code** | | | |
| Prompt → Code | ✅ Full autonomy | ✅ Basic | ✅ Done |
| Test writing | ✅ Agents write tests | ✅ Coder agent does this | ✅ Done |
| PR creation | ✅ Auto-create PR | ✅ PRManager | ✅ Done |
| Agent-to-agent review | ✅ Codex reviews Codex | ❌ Not yet | 🔲 Future |
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
| AGENTS.md as table of contents | ✅ Short (~100 lines) | ⚠️ Needs update | 🔲 Future |
| Structured docs/ | ✅ System of record | ❌ Not yet | 🔲 Future |
| Plans as first-class artifacts | ✅ Versioned plans | ✅ JSON plan | ✅ Done |
| Doc linters | ✅ CI validates docs | ❌ Not yet | 🔲 Future |

| **5. Architecture Enforcement** | | | |
| Layered architecture | ✅ Strict layers | ❌ Not enforced | 🔲 Future |
| Custom linters | ✅ Codex writes lints | ❌ Not yet | 🔲 Future |
| Taste invariants | ✅ Structured logging, naming | ❌ Not yet | 🔲 Future |
| Boundary validation | ✅ Mechanical enforcement | ❌ Not yet | 🔲 Future |

| **6. Autonomy Level** | | | |
| Validate current state | ✅ | ❌ Not yet | 🔲 Future |
| Reproduce bug | ✅ Video + repro | ❌ Not yet | 🔲 Future |
| Fix + validate fix | ✅ | ✅ Basic | 🔲 Future |
| Respond to feedback | ✅ Agent-agent loop | ❌ Not yet | 🔲 Future |
| Escalate to human | ✅ When judgment needed | ❌ Not yet | 🔲 Future |

| **7. Maintenance** | | | |
| Garbage collection | ✅ Cleanup agents | ❌ Not yet | 🔲 Future |
| Technical debt tracking | ✅ Quality grades | ❌ Not yet | 🔲 Future |
| Doc-gardening agent | ✅ Auto-fix stale docs | ❌ Not yet | 🔲 Future |

---

## Current AutoDev Status

### ✅ Implemented
1. GitHub issue fetching and parsing
2. Task decomposition (issue → features → subtasks)
3. Parallel agent execution with OpenCode
4. **Parallel agent execution with Claude Code** ⭐ NEW
5. Worktree management
6. Activity logger with full observability
7. Dashboard visualization
8. PR creation
9. Basic Slack integration
10. **Agent-to-agent code review** ✅
11. **Shared memory context** ⭐ NEW

### 🔲 Not Yet Implemented (Priority Order)

#### High Priority
1. ~~**Agent-to-agent code review** - Agents review each other's PRs~~ ✅ DONE!
2. **Auto-merge logic** - Wait for CI → merge
3. **Better knowledge base** - Update AGENTS.md, structured docs/

#### Medium Priority
4. **Chrome DevTools integration** - UI bug reproduction
5. **PromQL/LogQL access** - Give agents metric query ability
6. **Architecture linters** - Enforce layered structure
7. **Taste invariants** - Structured logging rules

#### Lower Priority
8. **Garbage collection agent** - Auto-cleanup
9. **Doc-gardening agent** - Fix stale docs
10. **Escalation logic** - Know when to ask humans

---

## Next Steps

See [README.md](./README.md) for updated roadmap.

*Generated: 2026-03-01*
