# AutoDev Pipeline Wiring — Design Spec

**Date:** 2026-03-31
**Status:** Approved
**Branch:** `fix/wire-pipeline-end-to-end`
**Target:** `main`

## Problem

The AutoDev pipeline stops dead after Phase 4 (feature list creation). Phases 5-8 are specified in markdown but never execute because:

1. **Phase 5** describes agent dispatch but the instructions don't result in actual `Agent` tool calls — the syntax is in code blocks that the LLM treats as example text
2. **Coder agent** can't call the researcher agent (no `Agent` in allowed-tools)
3. **Worktrees** are created but never cleaned up after merge
4. **`.autodev/`** is in `.gitignore`, so state can't persist across sessions
5. **Researcher agent** is never triggered when coder is stuck

## Changes

### 1. `commands/autodev.md` — Fix Phase 5 dispatch

**Current:** Phase 5 has pseudo-code in markdown code blocks:
```
Agent:
  type: coder
  isolation: worktree
  prompt: {prepared prompt}
```
This is treated as example text, not as an action.

**Fix:** Rewrite Phase 5 instructions to explicitly tell the LLM to:
- For each feature, construct a complete prompt that includes:
  - The feature ID, description, and subtasks from `feature_list.json`
  - The relevant files identified in Phase 3
  - The full coder agent instructions (read from `agents/coder.md`)
  - The current `agent-state.json` contents
- Dispatch all features in parallel using multiple `Agent` tool calls in a single message
- Each Agent call uses: `isolation: "worktree"`, `model: "sonnet"`, `run_in_background: true` for parallel execution
- After all agents complete, read their results and update `feature_list.json`

**Key instruction pattern:**
```
For each feature, use the Agent tool with these parameters:
- description: "Implement {feature_id}: {feature_name}"
- prompt: <the constructed prompt>
- isolation: "worktree"
- model: "sonnet"
- run_in_background: true

Dispatch ALL features in a single message so they run in parallel.
Then wait for all agents to complete before proceeding to Phase 6.
```

### 2. `commands/autodev.md` — Fix Phase 6 worktree cleanup

**Current:** Phase 6 describes merge but has no worktree cleanup.

**Fix:** After merging all feature branches, add explicit cleanup:
```bash
# For each feature worktree:
git worktree remove <worktree_path> --force
# Optionally delete feature branches after merge:
git branch -d autodev/{feat-id}-{slug}
```

### 3. `commands/autodev.md` — Fix Phase 7 reviewer dispatch

**Current:** Phase 7 has the right structure but uses code-block syntax.

**Fix:** Rewrite to explicitly instruct the LLM to use the Agent tool:
- Read all changed files via `git diff main...autodev/issue-{N} --stat`
- Construct reviewer prompt with the diff and reviewer instructions
- Dispatch single Agent call with `model: "opus"`
- Parse the returned VERDICT line
- If CHANGES_REQUESTED: dispatch a coder Agent (no worktree, on unified branch) with the issues list, then re-review (max 3 cycles)

### 4. `agents/coder.md` — Add researcher escalation

**Current:** `error_fix` skill says "if stuck after 3 attempts: stop and report your status." No researcher integration. `Agent` not in allowed-tools.

**Fix:**
- Add `Agent` to allowed-tools list
- Rewrite `error_fix` to track attempt count and escalate:
  1. Attempt 1-2: Debug and fix normally
  2. Attempt 3: Before giving up, dispatch a researcher Agent with:
     - The error message
     - What was tried
     - Relevant code context
  3. Apply researcher's findings and retry once more
  4. If still failing after researcher help: stop and report

### 5. `agents/coder.md` — Remove `.main_repo/` assumption

**Current:** References `.main_repo/.autodev/agent-state.json` for coordination.

**Fix:** When running in a Claude Code worktree, the worktree IS a full repo checkout. The `.autodev/` directory is at the worktree root. Remove all `.main_repo/` path prefixes. Agent-state coordination is best-effort — if the file doesn't exist, proceed without it.

### 6. `.gitignore` — Remove `.autodev/` exclusion

**Current:** `.autodev/` is listed in `.gitignore`, preventing state persistence.

**Fix:** Remove the `.autodev/` line. State files should be committed to git so they persist across sessions and enable multi-agent coordination.

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `commands/autodev.md` | Modify | Rewrite Phases 5-7 with explicit Agent dispatch instructions |
| `agents/coder.md` | Modify | Add Agent to allowed-tools, add researcher escalation, remove .main_repo/ |
| `.gitignore` | Modify | Remove `.autodev/` line |

## What stays unchanged

- `agents/researcher.md` — Already well-structured, no changes needed
- `agents/reviewer.md` — Already well-structured, no changes needed
- `skills/autodev/references/*` — Good specs, just need to be read by the pipeline
- Phases 0-4 in `autodev.md` — Working correctly

## Architecture decisions

1. **No Python code** — Pure Claude Code plugin wiring via markdown instructions
2. **Parallel dispatch** — Multiple Agent tool calls in a single message
3. **Worktree cleanup in Phase 6** — After successful merge, not before
4. **Researcher called by coder** — Coder knows when it's stuck, simpler than orchestrator-mediated
5. **Background agents** — `run_in_background: true` for parallel execution, orchestrator waits for completion notifications

## Success criteria

After these changes, `/autodev <issue>` should:
1. Parse, validate, explore, decompose (Phases 0-4, already working)
2. Actually dispatch coder agents in parallel worktrees (Phase 5)
3. Coder agents implement features, call researcher if stuck
4. Merge all feature branches, clean up worktrees (Phase 6)
5. Dispatch reviewer, handle feedback loop (Phase 7)
6. Push branch and report results (Phase 8)
