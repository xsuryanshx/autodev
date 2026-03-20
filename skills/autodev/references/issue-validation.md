# Issue Validation

## Overview

Before writing a single line of code, the initiator agent must validate the issue. This process determines whether the issue is real, reproducible, and actionable. Skipping validation is the single most common cause of wasted agent effort — implementing a fix for a misunderstood or already-resolved issue.

Validation runs entirely before any code changes. It is read-only: no files are modified, no branches are created.

---

## Validation Phases

### Phase 1: Parse

Extract structured information from the issue body.

For each issue, identify:

| Field | Where to Look | Example |
|-------|---------------|---------|
| **Expected behavior** | "Expected:", "should", "expected to" | "POST /login should return a 200 with a JWT token" |
| **Actual behavior** | "Actual:", "but", "instead", "however" | "Returns 500 Internal Server Error" |
| **Error messages** | Code blocks, "Error:", "Exception:", stack traces | `AttributeError: 'NoneType' object has no attribute 'encode'` |
| **Reproduction steps** | Numbered lists, "Steps to reproduce", "To reproduce" | 1. Run server 2. POST to /login 3. See error |
| **Environment info** | "Python 3.x", "version", "OS:", "Docker" | Python 3.11, Ubuntu 22.04 |
| **Referenced files** | Code blocks, backtick references, file paths | `src/auth/views.py line 42` |

If any of these fields are present, note them explicitly before proceeding to Phase 2.

### Phase 2: Classify

Determine the issue type. This determines which validation path to follow.

| Type | Characteristics | Validation Required |
|------|-----------------|---------------------|
| **Bug report** | Has actual/expected behavior, error messages, or reproduction steps | Full validation (Phases 3-4) |
| **Feature request** | "Add", "implement", "support for", no current broken behavior | Skip to Phase 4 directly |
| **Documentation** | Typo fix, clarify docs, update README | Minimal — verify the doc exists |
| **Question** | Ends in "?", no clear action requested | Flag as `NEEDS_INFO` |
| **Refactor** | "Clean up", "improve", "restructure", no functional change described | Treat as feature request |

If the type is ambiguous, default to treating it as a **bug report** and running full validation.

### Phase 3: Validate (Bug Reports Only)

Attempt to confirm the bug exists in the current codebase.

#### Step 3a: Run the Test Suite

Run the project's full test suite before doing anything else.

```bash
# Discover and run tests
# Python
pytest --tb=short 2>&1 | tail -20

# Node.js
npm test 2>&1 | tail -20

# Go
go test ./... 2>&1 | tail -20
```

- If an existing test fails and its name relates to the issue, the bug is confirmed.
- Record the test output in `.autodev/autodev-progress.txt`.
- Note the baseline: how many tests pass before any changes.

#### Step 3b: Search Codebase for Error Messages

If the issue contains specific error messages or exception names, search the codebase for related code.

```bash
# Search for the exception/error type
grep -r "AttributeError" src/ --include="*.py" -l
grep -r "NoneType" src/ --include="*.py" -n

# Search for referenced function/class names
grep -r "def login" src/ --include="*.py" -n
```

If the code path referenced in the error exists and looks potentially buggy, the issue is credible.

#### Step 3c: Follow Reproduction Steps

If reproduction steps are provided, attempt them.

```bash
# Example: if issue says "run server then POST to /login"
# Start server (in background, with timeout)
python manage.py runserver &
SERVER_PID=$!

# Attempt the reproduction
curl -X POST http://localhost:8000/login -H "Content-Type: application/json" \
  -d '{"username": "test", "password": "test"}' -v

kill $SERVER_PID
```

Record the actual output. Compare it to what the issue says should happen.

#### Step 3d: Check File References

If the issue references specific files or line numbers, verify they exist.

```bash
# Check referenced file exists
ls src/auth/views.py

# Check referenced function exists
grep -n "def authenticate" src/auth/views.py

# If line number mentioned, check the code there
sed -n '40,45p' src/auth/views.py
```

If the referenced file or function does not exist, the issue is likely stale (code was refactored) or the reporter made an error.

---

### Phase 4: Decision Gate

Based on Phases 1-3, assign a validation outcome.

| Outcome | Condition | Action |
|---------|-----------|--------|
| `VALID` | Confidence > 0.6 — bug reproduced, or code path clearly buggy, or test fails | Proceed with implementation |
| `LIKELY_VALID` | Confidence 0.3-0.6 — error code exists but couldn't reproduce, or reproduction steps incomplete | Proceed but flag uncertainty to user in progress file |
| `INVALID` | Confidence < 0.3 — cannot find relevant code, steps don't reproduce the error, or issue refers to non-existent code | Report findings, do NOT change code |
| `FEATURE_REQUEST` | Issue classified as feature in Phase 2 | Skip validation, proceed with implementation |
| `NEEDS_INFO` | Insufficient information to validate or implement | Report what's missing, do NOT change code |

**Default rule for bug reports:** If you cannot reproduce the bug and cannot find a clear code reference, default to `INVALID`. Do not change code on the assumption that there might be a bug somewhere.

---

## Confidence Scoring Guide

Use this rubric to estimate confidence for bug reports:

| Evidence | Confidence Weight |
|----------|------------------|
| Bug reproduced by following the steps exactly | +0.5 |
| Existing test fails with matching error | +0.4 |
| Error message found in codebase at a plausible failure point | +0.3 |
| Referenced file and function exist | +0.2 |
| Issue has clear expected vs actual behavior | +0.1 |
| Referenced file does NOT exist | -0.3 |
| Reproduction steps provided but don't reproduce the error | -0.2 |
| Issue is more than 6 months old (may be fixed already) | -0.1 |

Sum the applicable weights. Confidence is capped at 1.0.

Example: "Bug reproduced (+0.5) + referenced file exists (+0.2) + clear expected/actual (+0.1) = 0.8 → VALID"

---

## Reporting Validation Results

Write the validation outcome to `.autodev/autodev-progress.txt` before proceeding:

```
2024-01-15T10:30:00Z [initiator] Validation: VALID (confidence: 0.8)
2024-01-15T10:30:00Z [initiator] Evidence: reproduced 500 error on POST /login, AttributeError in src/auth/views.py:42
2024-01-15T10:30:00Z [initiator] Baseline: 47/47 tests passing before any changes
```

For `INVALID` or `NEEDS_INFO` outcomes, write a detailed report to the terminal output before stopping:

```
Validation outcome: INVALID

Issue #99 claims that POST /login returns 500, but:
- Reproduction steps could not be followed (no local server config found)
- grep for 'AttributeError' and 'NoneType' found no matches in src/
- The file src/auth/views.py referenced in the issue does not exist
  (closest match: src/authentication/views.py, which has no login view)

The issue may be stale or based on a different version of the codebase.

Recommendation: Ask the reporter to clarify which version they're using
and provide an updated file path.

No code changes were made.
```

---

## Special Cases

### Issue References a Dependency, Not the Repo

If the error originates in a third-party library (stack trace shows `site-packages/`), the fix may belong in the dependency, not this repo. Validate whether there is a workaround or version pin that this repo should apply.

### Issue is Already Fixed

Run the test suite. If all tests pass and you cannot reproduce the issue, it may have been fixed in a later commit. Check:

```bash
git log --oneline --since="6 months ago" --grep="<issue keywords>"
```

If a recent commit looks related, note it and mark the issue as `INVALID` (already resolved).

### Multiple Issues in One

If the issue body contains multiple distinct bug reports, validate each separately. The feature list should have one feature per distinct bug.
