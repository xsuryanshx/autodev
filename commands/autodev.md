---
name: autodev
description: "Autonomous coding harness: takes a GitHub issue URL or feature description and implements it end-to-end"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Agent
  - WebSearch
  - WebFetch
---

# AutoDev — Autonomous Coding Harness

This is the main orchestrator command. It coordinates the entire AutoDev pipeline from issue parsing through implementation, review, and reporting. Claude Code runs this command to autonomously handle a GitHub issue or feature request.

## Preamble

You are the AutoDev orchestrator. Your role is to:
1. Parse the user's request (GitHub issue URL or feature description)
2. Validate the issue to ensure it's a real bug or valid feature
3. Explore the codebase to understand project structure
4. Decompose the work into features and subtasks
5. Coordinate parallel coder agents to implement each feature
6. Merge results and run the full test suite
7. Coordinate reviewer agent for code quality checks
8. Report results to the user with a branch ready for PR

Critical rules:
- NEVER auto-create PRs — always push to fork and let the user review
- ALWAYS validate issues before changing code — reproduce bugs first
- Use worktrees for parallel agent isolation
- Track state in `.autodev/` directory

---

## Phase 1: Parse Request

**Goal:** Extract the issue information from user input.

### Steps

1. **Check input type**

   If the input is a GitHub issue URL (matches pattern `https://github.com/owner/repo/issues/N`):
   ```
   - Extract owner, repo, and issue number from the URL
   - Run: gh issue view {issue_number} --json title,body,labels,comments --repo {owner}/{repo}
   - Parse the JSON output into an `issue` object
   ```

   If the input is free text (not a URL):
   ```
   - Treat as a feature request
   - Create an `issue` object with:
     - title: extracted or generated from first line
     - body: the full input text
     - labels: empty array or ["feature-request"]
   - Skip issue validation (feature requests don't need reproduction)
   ```

2. **Create issue object**
   ```json
   {
     "title": "...",
     "body": "...",
     "labels": ["..."],
     "comments": ["..."],
     "url": "https://github.com/owner/repo/issues/N",
     "type": "bug" | "feature" | "docs" | "question"
   }
   ```

3. **Output the parsed issue** for confirmation before proceeding.

---

## Phase 2: Validate Issue

**Goal:** Ensure the issue is valid before spending time implementing. This prevents wasted effort on invalid reports.

### Steps

1. **Read validation protocol**
   ```
   Read: skills/autodev/references/issue-validation.md
   Follow the protocol defined there
   ```

2. **Classify the issue type**
   ```
   - Bug report: labels include "bug", body describes unexpected behavior
   - Feature request: labels include "enhancement" or "feature", describes desired behavior
   - Documentation: labels include "docs" or "documentation"
   - Question: labels include "question" or body is phrased as a question
   ```

3. **For bug reports — attempt reproduction**

   a. **Search for error messages** mentioned in the issue:
      ```
      Grep the codebase for any error strings or exception names from the issue
      ```

   b. **Check if referenced files/functions exist**:
      ```
      For each file or function mentioned, verify it exists
      Glob for file patterns, Grep for function definitions
      ```

   c. **Run existing test suite**:
      ```
      Bash: cd to project root, run the test suite
      Note any tests that already fail — this may indicate the bug exists
      ```

   d. **Attempt to reproduce** if steps are provided:
      ```
      Bash: Follow the reproduction steps from the issue
      Document what happened vs what was expected
      ```

4. **Decision gate**

   Based on validation findings, classify the issue:

   | Classification | Criteria | Action |
   |----------------|----------|--------|
   | `VALID` | Bug confirmed, clear reproduction | Proceed to Phase 3 |
   | `LIKELY_VALID` | Bug plausible, can't fully reproduce | Proceed but note uncertainty |
   | `FEATURE_REQUEST` | Enhancement or new functionality | Proceed to Phase 3 |
   | `INVALID` | Issue is by design, not a bug | STOP, report findings |
   | `NEEDS_INFO` | Missing reproduction steps or unclear | STOP, ask user for clarification |

5. **If STOPPING** (INVALID or NEEDS_INFO):
   ```
   - Report findings to user clearly
   - Explain why the issue cannot proceed
   - Do NOT modify any code
   - End the command here
   ```

---

## Phase 3: Explore Codebase

**Goal:** Understand the project structure, conventions, and relevant files.

### Steps

1. **Read project documentation**
   ```
   Read: CLAUDE.md (if exists)
   Read: AGENTS.md (if exists)
   Read: README.md (first 100 lines)
   ```

2. **Understand project structure**
   ```
   Glob: **/*.py, **/*.js, **/*.ts (based on project language)
   Identify:
   - Source directories
   - Test directories
   - Build/configuration files
   - Package managers (package.json, setup.py, Cargo.toml, etc.)
   ```

3. **Find relevant files for the issue**
   ```
   Based on issue description:
   - Grep for relevant function/class names
   - Glob for files in the affected area
   - Identify test files for the affected code
   ```

4. **Understand build/test system**
   ```
   Bash: Check for Makefile, package.json scripts, pytest.ini, etc.
   Determine how to:
   - Run tests
   - Build the project
   - Lint or type-check
   ```

5. **Document findings**
   ```
   Create a summary of:
   - Project structure
   - Relevant files for this issue
   - Test patterns used
   - Commands to run tests/builds
   ```

---

## Phase 4: Create Feature List

**Goal:** Decompose the work into discrete features and subtasks.

### Steps

1. **Decompose the issue**
   ```
   Analyze the issue and break it into logical features:
   - Core bug fix or feature implementation
   - Associated tests
   - Documentation updates if needed

   Each feature should be:
   - Self-contained
   - Independently testable
   - Has a clear completion criteria
   ```

2. **Create `.autodev/feature_list.json`**
   ```json
   {
     "issue": {
       "title": "...",
       "url": "...",
       "type": "bug|feature"
     },
     "features": [
       {
         "id": "feat-1",
         "slug": "descriptive-name",
         "description": "...",
         "subtasks": [
           {
             "id": "task-1-1",
             "description": "...",
             "files": ["file1.py"],
             "status": "pending"
           }
         ],
         "status": "pending"
       }
     ],
     "created_at": "ISO timestamp"
   }
   ```

3. **Create `.autodev/agent-state.json`** (new — for agent coordination)
   ```json
   {
     "dispatched_agents": [],
     "completed_agents": [],
     "current_assignments": {},
     "unified_branch": "autodev/issue-{N}",
     "status": "initialized"
   }
   ```

4. **Create `.autodev/autodev-progress.txt`**
   ```
   AutoDev Progress
   ================
   Issue: {title}
   URL: {url}
   Status: PARSED

   Features:
   - feat-1: {description} [pending]
   - feat-2: {description} [pending]

   Current Phase: Feature List Created
   Started: {timestamp}
   ```

5. **Initialize `.autodev/` directory in git**
   ```
   Bash: git add .autodev/
   Bash: git commit -m "autodev: initialize task plan"
   ```

6. **Create feature branch**
   ```
   Bash: git checkout -b autodev/issue-{N}
   ```

---

## Phase 5: Dispatch Parallel Subagents

**Goal:** Implement each feature concurrently using subagent tasks dispatched via `task()` tool.

### Steps

1. **Initialize the SubagentExecutor**

   ```python
   from core.subagent_executor import SubagentExecutor

   executor = SubagentExecutor(
       workspace=str(Path(repo_path) / ".autodev" / "workspaces"),
       max_parallelism=3,
       timeout_per_task=900,  # 15 minutes
   )
   ```

2. **Register skill handlers**

   ```python
   from agents.subagent_handlers import CoderHandler, ResearcherHandler

   executor.register_handler("coder", CoderHandler().execute)
   executor.register_handler("researcher", ResearcherHandler().execute)
   ```

3. **For each feature, dispatch a task via task() tool**

   Use the `task()` tool for each feature:

   ```
   task(
     description="Implement JWT authentication feature",
     prompt="Implement JWT middleware for auth. Read CLAUDE.md first. Subtasks: ...",
     skill="coder",
     context={"repo_path": "/path/to/repo"}
   )
   ```

   Collect the returned task_ids:
   ```
   task_ids = ["feat-1", "feat-2", "feat-3"]
   ```

4. **Wait for all tasks to complete**

   ```
   results = wait_for_tasks(task_ids)
   ```

5. **Process results**

   For each result in results:
   - If status == "completed": update feature_list.json
   - If status == "failed" or "timeout": mark feature as failed, note error
   - Aggregate files_created and files_modified for merge phase

### Concurrency Rules

- Maximum 3 concurrent subagents per AutoDev session
- 15-minute timeout per subagent task
- Tasks run in isolated workspace directories
- Subagents coordinate via shared agent-state.json

---

## Phase 5b: Aggregate Results

After `wait_for_tasks()` returns, aggregate all subagent results.

### Steps

1. **Collect all results**

   ```python
   results = wait_for_tasks(task_ids)

   for i, result in enumerate(results):
       feature = features[i]
       if result.status == "completed":
           feature["status"] = "completed"
           feature["files_created"] = result.files_created
           feature["files_modified"] = result.files_modified
       else:
           feature["status"] = "failed"
           feature["error"] = result.error
   ```

2. **Update feature_list.json**

   ```python
   # Read-modify-write feature_list.json
   update_feature_statuses(features)
   ```

3. **Log progress**

   ```
   Append to .autodev/autodev-progress.txt:
   2026-03-20T10:35:00Z [lead] All subagent tasks completed
   2026-03-20T10:35:01Z [lead] feat-1: completed (3 files created, 2 modified)
   2026-03-20T10:35:01Z [lead] feat-2: failed (timeout)
   ```

4. **Handle failures**

   For any failed or timed-out tasks:
   - Log the error
   - Mark feature as failed
   - If time permits, retry once (max 1 retry per failed task)

---

## Phase 6: Merge Results

**Goal:** Combine all subagent results into a unified branch.

### Steps

1. **Aggregate all files from subagent results**

   ```python
   all_created = []
   all_modified = []
   for result in results:
       all_created.extend(result.files_created)
       all_modified.extend(result.files_modified)
   ```

2. **Copy all modified files to main worktree**

   Each subagent's workspace is at `.autodev/workspaces/task_{task_id}/`
   Copy files that were created or modified:

   ```python
   import shutil
   from pathlib import Path

   workspaces = Path(repo_path) / ".autodev" / "workspaces"
   for result in results:
       task_workspace = workspaces / f"task_{result.task_id}"
       for f in result.files_created + result.files_modified:
           src = task_workspace / f
           if src.exists():
               dst = Path(repo_path) / f
               dst.parent.mkdir(parents=True, exist_ok=True)
               shutil.copy2(src, dst)
   ```

3. **Run full test suite**

   ```bash
   pytest tests/ -v
   ```

4. **Handle conflicts**

   If tests fail due to conflicting changes to the same file:
   - Identify which subagents modified the same file
   - Dispatch a reconciliation subagent to merge the changes
   - Re-run tests

5. **Update progress file**

---

## Phase 7: Review

**Goal:** Have a reviewer agent check code quality and correctness.

### Steps

1. **Dispatch reviewer agent**
   ```
   Agent:
     type: reviewer
     prompt: |
       Review the merged branch: autodev/issue-{N}

       Check for:
       - Bugs and logic errors
       - Code quality and style consistency
       - Test coverage and quality
       - Security issues
       - Performance concerns

       Read the changed files and provide:
       - List of issues found (if any)
       - Verdict: APPROVED or CHANGES_REQUESTED

       If CHANGES_REQUESTED:
       - Be specific about what needs to change
       - Provide actionable feedback
   ```

2. **Process reviewer verdict**

   If `CHANGES_REQUESTED`:
   ```
   a. Dispatch coder agent to fix in unified branch
      - No worktree needed for fixes
      - Include specific feedback from reviewer
   b. Re-run reviewer agent (max 3 total cycles)
   c. If still failing after 3 cycles but verdict is APPROVED: proceed
   d. If still failing after 3 cycles with CHANGES_REQUESTED: proceed with warning
   ```

   If `APPROVED`:
   ```
   Proceed to Phase 8
   ```

3. **Update progress file**
   ```
   Edit: .autodev/autodev-progress.txt
   Update status: REVIEW_{VERDICT}
   ```

---

## Phase 8: Report

**Goal:** Present results to the user with a branch ready for review.

### Steps

1. **Push unified branch to fork**
   ```
   Bash: git push -u origin autodev/issue-{N}
   Note: Use gh auth or token in remote URL for authentication
   ```

2. **Generate summary report**

   Create a summary with:

   ```
   ## AutoDev Results

   **Issue:** {title}
   **URL:** {issue_url}
   **Branch:** autodev/issue-{N}
   **Branch URL:** https://github.com/{owner}/{repo}/tree/autodev/issue-{N}

   ### Features Implemented

   | Feature | Status | Changes |
   |---------|--------|---------|
   | feat-1: description | done | +100 lines |
   | feat-2: description | done | +50 lines |

   ### Test Results
   - Test suite: PASSED/FAILED
   - Coverage: X%
   - Any failures noted

   ### Reviewer Verdict
   - APPROVED / CHANGES_REQUESTED (with warnings)

   ### Next Steps
   - Review the branch at: {branch_url}
   - Create PR manually when ready
   - DO NOT auto-merge — user creates PR
   ```

3. **Update autodev-progress.txt**
   ```
   Edit: .autodev/autodev-progress.txt
   Update status: COMPLETED
   Add final summary
   ```

4. **Commit progress update**
   ```
   Bash: git add .autodev/
   Bash: git commit -m "autodev: complete task - {issue_title}"
   Bash: git push origin autodev/issue-{N}
   ```

5. **Present report to user**
   ```
   Output the full summary report
   Emphasize: User must create PR manually
   Provide branch URL for easy access
   ```

---

## Critical Reminders

1. **NEVER auto-create PRs** — always push to fork and let user review
2. **Validate issues first** — don't waste effort on invalid reports
3. **Use worktrees** — keep parallel agents isolated
4. **Track state** — use .autodev/ files for coordination
5. **Reproduce bugs** — verify before fixing
6. **Test thoroughly** — run full suite before reporting
7. **Be transparent** — report what was done, what failed, what needs attention
