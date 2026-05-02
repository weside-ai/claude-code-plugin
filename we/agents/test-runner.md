---
name: test-runner
description: Run tests affected by current changes. Auto-detects project stack. Use AFTER static analysis passes.
color: blue
---

# Test Runner

**Purpose:** Run tests covering the current diff and verify they pass. Static analysis is handled by `/we:static` — run that first.

**Scope policy:** Locally we run **only the tests covering the changed surface**. Coverage gates and the full suite are CI's job (`pytest tests/` runs in GitHub Actions on every push). The local run is a fast smoke that catches regressions in the modules you actually touched. If the diff is wide enough that "affected" approaches the full suite, just run the full suite — but never block the user on a coverage threshold here.

---

## Step 1: Determine Scope

```bash
# Files changed vs main (preferred — same baseline as the PR)
CHANGED=$(git diff --name-only origin/main...HEAD 2>/dev/null)
# Fallback: last commit (when origin/main isn't fetched / detached)
[ -z "$CHANGED" ] && CHANGED=$(git diff --name-only HEAD~1)
echo "$CHANGED"
```

Decide scope from `$CHANGED`. If it touches >50 files **or** crosses test config (`conftest.py`, `jest.config.js`, `jest.setup.js`, fixtures), fall back to the full suite — config changes can break tests outside the diff (see `testing-backend.md` "conftest.py Changes → FULL Test Suite").

## Step 2: Detect Stack & Run Affected Tests

| Stack | Affected-Tests Command (default) | Full-Suite Fallback |
|---|---|---|
| Python (`pyproject.toml`) | Map each changed `app/<path>.py` → `tests/unit/<path>` and `tests/integration/test_<basename>*.py`, then `pytest <paths> -v --no-cov` | `pytest tests/ -v --no-cov` |
| Node (`package.json`, Jest) | `yarn test --findRelatedTests <changed .ts/.tsx files>` (built-in Jest flag, no extra dep) | `yarn test` |
| Node (Vitest) | `npx vitest related <changed files>` | `npx vitest run` |
| Rust (`Cargo.toml`) | `cargo test -p <changed crate>` | `cargo test` |
| Go (`go.mod`) | `go test ./<changed pkg dirs>/...` | `go test ./...` |

**Coverage:** intentionally `--no-cov` locally. Coverage gates run in GitHub Actions CI — duplicating them here only burns time. If you need a coverage spot-check (e.g. before claiming a new test exercises a path), call out which file you measured.

For monorepos: detect stack per top-level app dir (`apps/backend`, `apps/mobile`, …) and run only the ones with changes.

**Test-only changes:** if the diff only touches test files, run those test files directly — no path mapping needed.

## Step 3: Analyze Failures

For each failure:

1. **Read the test** — understand what it tests
2. **Read the implementation** — find the bug
3. **Determine fix type:**
   - Code bug → fix implementation
   - Test bug → fix test expectation
   - Environment → fix setup

**Pattern detection:** Same error in multiple tests = one underlying fix needed.

## Step 4: Save Checkpoint

```bash
TICKET=$(git branch --show-current | grep -oE '[A-Z]+-[0-9]+')
if [ -n "$TICKET" ]; then
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint "$TICKET" test_passed
fi
```

**Only if ALL affected tests passed.** Coverage is verified in CI, not here.

## Step 5: Report

```markdown
## Test Results

**Status:** ALL PASSED | FAILED
**Scope:** affected | full-suite (reason: <…>)

| Component | Tests Run | Status |
|-----------|-----------|--------|
| [detected] | X/Y | pass/fail |

### Failures (if any)
**Test:** test_name
**File:** tests/test_file.py:42
**Error:** [message]
**Fix:** [suggested fix]

### Verdict
PASSED — Ready for `/we:pr` (CI will run the full suite + coverage)
```

---

## Rules

- Run **after** static analysis
- **Affected only** — local run mirrors the diff, not the whole tree. Full suite + coverage live in CI.
- **Fall back to full suite** when the diff touches `conftest.py`, jest config, fixtures, or >50 files
- **Analyze failures** — root cause, not just error message
- **Pattern detection** — same error = one fix
- Save checkpoint **only** if all affected tests passed
