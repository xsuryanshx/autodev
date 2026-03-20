# Merge Strategy

## Overview

Each coder agent works in an isolated git worktree on its own feature branch. After all agents complete, the orchestrator merges all feature branches into a single unified branch. That unified branch is the final deliverable — it is never auto-submitted as a PR.

---

## Branch Naming

| Branch Type | Format | Example |
|-------------|--------|---------|
| Feature branch (per agent) | `autodev/<feat-id>-<slug>` | `autodev/feat-1-user-auth` |
| Unified branch | `autodev/issue-<N>` | `autodev/issue-42` |

`<slug>` is a kebab-case version of the feature name, truncated to 40 characters.

---

## Step-by-Step Merge Process

### Step 1: Verify All Agents Are Done

Before starting the merge, confirm that every feature is in a terminal state (`completed` or `failed`) in `feature_list.json`. Do not begin merging while any feature is `in_progress`.

```bash
# Check feature statuses
cat .autodev/feature_list.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for f in data['features']:
    print(f['id'], f['status'])
"
```

If any feature is `failed`, decide whether to proceed with the remaining features or abort. Partial merges are acceptable — document which features were excluded in `.autodev/autodev-progress.txt`.

### Step 2: Create the Unified Branch

Start the unified branch from the base branch of the target repository (typically `main` or `master`).

```bash
# Determine base branch
BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@')

# Create unified branch from base
git checkout -b autodev/issue-42 origin/$BASE_BRANCH
```

### Step 3: Merge Each Feature Branch

Merge feature branches one at a time, in order of their `id`. Sequential merging gives you a clean conflict resolution path — each conflict is isolated to one merge operation.

```bash
# For each completed feature branch, in order:
git merge --no-ff autodev/feat-1-user-auth \
  -m "merge: feat-1 user auth implementation"

git merge --no-ff autodev/feat-2-rate-limit-config \
  -m "merge: feat-2 rate limit config"
```

Use `--no-ff` (no fast-forward) to preserve each feature as a distinct merge commit in the history. This makes the contribution of each agent auditable.

### Step 4: Conflict Resolution

If `git merge` exits with conflicts, follow this resolution sequence:

#### 4a: Attempt Auto-Resolution

```bash
# Check which files have conflicts
git diff --name-only --diff-filter=U

# For each conflicted file, try auto-resolution strategies:

# Strategy 1: Use the incoming branch's version (the feature branch)
# Use when: the feature branch added new code and base doesn't have it
git checkout --theirs path/to/conflicted_file.py
git add path/to/conflicted_file.py

# Strategy 2: Use the current branch's version (unified branch so far)
# Use when: the current version is more complete and the feature only touched a subset
git checkout --ours path/to/conflicted_file.py
git add path/to/conflicted_file.py

# Strategy 3: Read both versions and write a merged version manually
# Use for: import blocks, configuration dicts, function additions to the same file
git diff path/to/conflicted_file.py   # shows conflict markers
# Edit file to resolve, then:
git add path/to/conflicted_file.py
```

#### 4b: Validate After Auto-Resolution

After resolving all conflicts in a merge, run the test suite before committing.

```bash
# Run tests to verify resolution is correct
<project test command>  # e.g., pytest, npm test, go test ./...

# If tests pass, complete the merge commit
git commit -m "merge: feat-N <name> (conflict resolved in <file>)"

# If tests fail, investigate — the resolution may have introduced a regression
```

#### 4c: Unresolvable Conflicts

If a conflict cannot be auto-resolved and manual resolution would require deep knowledge of the feature logic:

1. Abort the merge for this feature branch:
   ```bash
   git merge --abort
   ```
2. Record the conflict in `.autodev/autodev-progress.txt`:
   ```
   2024-01-15T12:00:00Z [orchestrator] feat-3 merge conflict in src/config.py — unresolvable, skipped
   ```
3. Continue merging the remaining feature branches.
4. Report the unresolved conflict to the user in the final output.

### Step 5: Run Full Test Suite

After all merges are complete, run the full test suite on the unified branch.

```bash
<project test command>
```

If tests fail:
- Identify which feature's merge introduced the regression using `git bisect` or by inspecting the merge commits.
- Attempt to fix the regression.
- If the fix is straightforward, commit it on the unified branch with message `fix: resolve regression from feat-N merge`.
- If the fix is not straightforward, document it and report to the user.

### Step 6: Push the Unified Branch

Push the unified branch to the user's fork (never to the upstream repository).

```bash
# Push to fork — always use token-authenticated URL
PUSH_URL="https://${GITHUB_TOKEN}@github.com/${FORK_OWNER}/${REPO_NAME}.git"
git push "$PUSH_URL" autodev/issue-42
```

### Step 7: Report to User

Output the branch URL for the user to review:

```
AutoDev session complete.

Unified branch: autodev/issue-42
Branch URL: https://github.com/<fork-owner>/<repo>/tree/autodev/issue-42

Features merged:
  feat-1: user auth — completed
  feat-2: rate limit config — completed
  feat-3: webhook handler — FAILED (merge conflict in src/config.py, skipped)

Review the branch and create a PR manually when ready.
```

---

## Critical Rule: Never Auto-Create a PR

AutoDev MUST NOT create a pull request automatically, even if the merge was clean and all tests pass. The user must review the changes and create the PR themselves.

Reasons:
- The agent may have introduced subtle bugs that only a human reviewer can catch.
- The PR description and title should be written by a human who understands the full context.
- Automated PRs to main repositories can merge breaking changes before anyone reviews them.

Always end a session by printing the branch URL and instructions for creating the PR manually.

---

## Conflict Prevention (Advisory)

The shared state protocol (`shared-state-protocol.md`) allows agents to post "claim" messages when they start working on a file. Reading these claims at the start of a session can reduce the number of conflicts at merge time.

However, since each agent works in its own isolated worktree, it cannot physically prevent another agent from editing the same file. Conflict prevention is advisory only. The merge process above is the authoritative conflict resolution mechanism.
