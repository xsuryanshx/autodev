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
- **ASK QUESTIONS FIRST** — understand the issue deeply before implementing

---

## Phase 0: Requirements Clarification

**Goal:** Understand the issue deeply before writing any code. This is a **hard gate** — no implementation until you understand the purpose, constraints, and success criteria.

**Inspired by:** superpowers:brainstorming skill — one question at a time, multiple choice preferred, understand before proposing.

### Principles

1. **One question per message** — don't overwhelm with multiple questions
2. **Multiple choice preferred** — easier for users to answer
3. **Focus on three axes:**
   - **Purpose** — What is this supposed to do? Why?
   - **Constraints** — Any technical limits? Existing patterns to follow?
   - **Success criteria** — How will we know it's done?
4. **Propose approaches after understanding** — never jump straight to implementation

### Question Sequence

Start with a **diagnostic question** to understand context:

```
I've received this issue:

**{issue_title}**
{issue_body}

Before I start implementing, I have a few questions to make sure I understand this correctly:

**Q1: What is the primary goal of this change?**
A) Fix a bug (something isn't working)
B) Add new functionality (something is missing)
C) Improve existing functionality (make it better)
D) Refactor (improve structure without changing behavior)
```

Based on the answer, follow up with targeted questions:

**If A (Bug):**
```
Q2: What is the expected behavior vs actual behavior?
[User describes]

Q3: What error message or crash occurs? (if any)
[User describes]

Q4: What are the reproduction steps?
[User describes]
OR
Q4: Can you describe the environment? (browser, OS, language version, etc.)
[User describes]
```

**If B (New functionality):**
```
Q2: Who will use this feature and why?
[User describes]

Q3: What should happen when it's working? (success scenario)
[User describes]

Q4: Are there any constraints I should know about?
A) Must integrate with existing {X} system
B) Must follow {language/framework} patterns
C) Performance is critical — needs to handle {N} requests/second
D) No specific constraints
```

**If C (Improve):**
```
Q2: What specifically should be improved?
[User describes]

Q3: Why is the current approach insufficient?
[User describes]

Q4: What would better look like?
[User describes]
```

**If D (Refactor):**
```
Q2: What code needs refactoring?
[User describes]

Q3: Why does it need refactoring?
A) Hard to maintain / understand
B) Performance issues
C) Security concerns
D) Technical debt accumulation
```

### Propose Approaches

After understanding, propose 2-3 approaches with trade-offs:

```
Based on your answers, here are 2-3 ways I could approach this:

**Option A: [Name]**
Pros: [benefit 1], [benefit 2]
Cons: [downside 1]
Best if: [when to use this]

**Option B: [Name]**
Pros: [benefit 1]
Cons: [downside 1], [downside 2]
Best if: [when to use this]

**My recommendation:** Option A because [reasoning]

Which approach would you prefer?
```

### Exit Criteria

**Do NOT proceed to Phase 1 until you have:**
- [ ] Classified the issue type (bug/feature/improvement/refactor)
- [ ] Understood the expected behavior or desired outcome
- [ ] Identified any constraints (technical, performance, integration)
- [ ] Confirmed success criteria
- [ ] User has approved the approach (or explicitly said "just do it")

### If User Says "Just Do It"

If the user is impatient and says "just do it" or similar:
- Acknowledge: "I'll proceed with reasonable defaults, but may ask clarifying questions if I get stuck"
- Still ask the most critical question (usually: bug vs feature vs improvement)
- Document any assumptions in the feature list

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

## Phase 5: Dispatch Parallel Coder Agents

**Goal:** Implement each feature in parallel using isolated worktrees.

### Steps

1. **Read current state**
   - Read `.autodev/agent-state.json` and `.autodev/feature_list.json`
   - Read `agents/coder.md` to get the full coder agent instructions

2. **For each feature, construct its prompt.** The prompt MUST include:
   - The feature ID, name, description, and full subtask list from `feature_list.json`
   - The relevant files identified in Phase 3
   - The project conventions (from CLAUDE.md or AGENTS.md if they exist in the target repo)
   - The test command discovered in Phase 3
   - The full content of `agents/coder.md` (so the agent knows its role and skills)
   - Explicit instruction: "You are working in an isolated worktree. Implement the feature, write tests, run the test suite, commit your changes, and report what you did."

3. **Dispatch ALL features in parallel using the Agent tool.**

   Send a SINGLE message containing one Agent tool call per feature. This is critical — sending them in one message makes them run in parallel.

   For each feature, use the Agent tool with these exact parameters:
   - `description`: "Implement {feat_id}: {short feature name}"
   - `prompt`: The constructed prompt from step 2
   - `isolation`: "worktree"
   - `model`: "sonnet"
   - `run_in_background`: true

   Example (for 2 features — adapt to however many you have):
   ```
   Agent call 1:
     description: "Implement feat-1: user authentication"
     prompt: <full prompt for feat-1>
     isolation: "worktree"
     model: "sonnet"
     run_in_background: true

   Agent call 2:
     description: "Implement feat-2: API rate limiting"
     prompt: <full prompt for feat-2>
     isolation: "worktree"
     model: "sonnet"
     run_in_background: true
   ```

   **Important:** If there is only 1 feature, you can use `run_in_background: false` and wait inline.

4. **Wait for all agents to complete.**
   Background agents will notify you when they finish. Do NOT poll or sleep.
   As each agent completes, read its result and note:
   - What was implemented
   - Files modified
   - Test results (pass/fail)
   - Final commit SHA
   - Any errors or blockers

5. **Update state files.**
   - Update `.autodev/feature_list.json`: set each feature's status to `completed` or `failed` based on agent results
   - Update `.autodev/agent-state.json`: record each agent's files_modified, status, feature, and commit
   - Append to `.autodev/autodev-progress.txt`: log completion of each feature with timestamp
   - Commit the state update: `git add .autodev/ && git commit -m "autodev: update state after Phase 5"`

6. **If any feature failed:** Note it in the progress file but continue to Phase 6 with whatever succeeded. Report failures in Phase 8.

---

## Phase 6: Merge Results and Cleanup Worktrees

**Goal:** Combine all feature branches into a unified branch, validate, and clean up worktrees.

### Steps

1. **Read merge strategy**
   Read `skills/autodev/references/merge-strategy.md` and follow the protocol.

2. **Checkout unified branch**
   ```bash
   git checkout autodev/issue-{N}
   ```

3. **Merge each completed feature branch** (in order of feature ID):
   ```bash
   git merge <feature-branch> --no-ff -m "Merge feature: {feat-id} — {feature name}"
   ```

   If a merge conflict occurs:
   - Read the conflicting files to understand both sides
   - Resolve the conflict by choosing the correct implementation (or combining both if they touch different parts)
   - Stage resolved files: `git add <resolved files>`
   - Complete the merge: `git commit`
   - If you cannot resolve a conflict, stop and report it to the user with details about both sides

4. **Clean up worktrees and branches.** After ALL merges are complete:
   ```bash
   # List all worktrees to find the ones created in Phase 5
   git worktree list

   # Remove each feature worktree (the paths returned by the agents)
   git worktree remove <worktree_path> --force

   # Delete local feature branches that have been merged
   git branch -d autodev/{feat-id}-{slug}

   # Delete remote feature branches (they were only needed for worktree creation)
   git push origin --delete autodev/{feat-id}-{slug}

   # Also clean up any worktree-agent-* branches left by Claude Code's isolation
   git branch | grep worktree-agent | xargs git branch -D
   git worktree prune
   ```

   **Important:** Only remove worktrees for features that were successfully merged. If a feature failed, leave its worktree for debugging.

5. **Run full test suite**
   Use the test command discovered in Phase 3. Example:
   ```bash
   pytest tests/ -v
   # or: npm test, cargo test, etc.
   ```

6. **If tests fail:**
   - Analyze the failure output to identify which tests broke and why
   - Dispatch a single coder Agent (NO worktree, NO background — run inline on the unified branch) to fix the failures:
     ```
     Agent tool:
       description: "Fix test failures on unified branch"
       prompt: <include test output, failing test names, and relevant code>
       model: "sonnet"
     ```
   - Re-run the full test suite after the fix
   - Maximum 2 retry cycles. If still failing after 2 retries, proceed to Phase 7 but note the failures

7. **Update state and commit**
   - Append to `.autodev/autodev-progress.txt`: "All features merged, worktrees cleaned up, tests {PASSED|FAILED}"
   - Commit: `git add .autodev/ && git commit -m "autodev: merge complete, worktrees cleaned"`

---

## Phase 7: Review

**Goal:** Have a reviewer agent check code quality and correctness.

### Steps

1. **Gather the diff for review.**
   ```bash
   git diff main...autodev/issue-{N} --stat
   git diff main...autodev/issue-{N}
   ```
   Save the diff output — you'll include it in the reviewer prompt.

2. **Read the reviewer agent instructions.**
   Read `agents/reviewer.md` to get the full reviewer role definition and output format.

3. **Dispatch the reviewer agent** using the Agent tool:
   - `description`: "Review autodev/issue-{N} changes"
   - `prompt`: Include:
     - The full content of `agents/reviewer.md`
     - The diff from step 1
     - The list of features implemented (from `feature_list.json`)
     - The test results from Phase 6
     - Instruction: "Review this code and output your verdict in the exact structured format defined in your instructions."
   - `model`: "opus"

   Do NOT use `run_in_background` — wait for the reviewer inline.

4. **Parse the reviewer's response.**
   Look for the `VERDICT:` line in the agent's output:
   - If `VERDICT: APPROVED` — proceed to Phase 8
   - If `VERDICT: CHANGES_REQUESTED` — go to step 5

5. **Handle CHANGES_REQUESTED** (max 3 review cycles total):

   a. Extract the `ISSUES:` list from the reviewer's output
   b. Dispatch a coder Agent to fix the issues (inline, no worktree, on the unified branch):
      - `description`: "Fix review issues on unified branch"
      - `prompt`: Include the reviewer's issues list, the affected files, and instruction to fix each issue
      - `model`: "sonnet"
   c. Re-run the full test suite to verify the fixes didn't break anything
   d. Re-dispatch the reviewer agent (repeat from step 3)
   e. If still `CHANGES_REQUESTED` after 3 total cycles: proceed to Phase 8 with a warning that review issues remain

6. **Update state**
   - Append to `.autodev/autodev-progress.txt`: "Review verdict: {VERDICT}, confidence: {CONFIDENCE}"
   - Commit: `git add .autodev/ && git commit -m "autodev: review {VERDICT}"`

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

## Cleanup on Failure

If the pipeline fails or is interrupted at ANY phase after Phase 5, you MUST clean up before stopping:

```bash
# 1. Remove all worktrees created by this run
git worktree list
# For each worktree that is NOT the main repo:
git worktree remove <path> --force

# 2. Prune stale worktree references
git worktree prune

# 3. Delete orphaned worktree-agent-* branches (created by Claude Code isolation)
git branch | grep worktree-agent | xargs git branch -D 2>/dev/null

# 4. Delete feature branches that were never merged
git branch | grep autodev/feat | xargs git branch -D 2>/dev/null
```

This cleanup runs even if:
- An agent failed and Phase 6 merge was skipped
- The reviewer rejected changes and you're stopping
- The user cancelled the run
- Any unexpected error occurred

**Never leave stale worktrees behind.** They waste disk space and pollute the branch list.

---

## Critical Reminders

1. **NEVER auto-create PRs** — always push to fork and let user review
2. **Validate issues first** — don't waste effort on invalid reports
3. **Use worktrees** — keep parallel agents isolated
4. **Track state** — use .autodev/ files for coordination
5. **Reproduce bugs** — verify before fixing
6. **Test thoroughly** — run full suite before reporting
7. **Be transparent** — report what was done, what failed, what needs attention
8. **Always clean up worktrees** — run cleanup on success AND failure
