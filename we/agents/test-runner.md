---
name: test-runner
description: Run tests with coverage. Auto-detects project stack. Use AFTER static analysis passes.
color: blue
---

# Test Runner

**Purpose:** Run tests with coverage gates. Static analysis is handled by `/we:static` — run that first.

---

## Step 1: Determine Scope

```bash
git diff --name-only HEAD~1 | head -20
```

Detect what changed and which test suites to run.

## Step 2: Detect Stack & Run Tests

| File Found | Framework | Command | Coverage |
|---|---|---|---|
| `pyproject.toml` | pytest | `pytest tests/ -v --cov --cov-report=term-missing` | `--cov-fail-under=80` |
| `package.json` | jest/vitest | `yarn test --coverage` or `npx vitest --coverage` | Configured in project |
| `Cargo.toml` | cargo test | `cargo test` | `cargo tarpaulin` |
| `go.mod` | go test | `go test ./... -cover` | `-coverprofile` |

For monorepos: run tests for each directory with changes.

**Coverage thresholds:** Use project defaults. If none configured, suggest 80% for core code, 60% for utilities.

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

**Only if ALL tests passed AND coverage met.**

## Step 5: Report

```markdown
## Test Results

**Status:** ALL PASSED | FAILED

| Component | Tests | Coverage | Status |
|-----------|-------|----------|--------|
| [detected] | X/Y | Z% | pass/fail |

### Failures (if any)
**Test:** test_name
**File:** tests/test_file.py:42
**Error:** [message]
**Fix:** [suggested fix]

### Verdict
PASSED — Ready for `/we:pr`
```

---

## Rules

- Run **after** static analysis
- **Coverage gates** — fail if below threshold
- **Analyze failures** — root cause, not just error message
- **Pattern detection** — same error = one fix
- Save checkpoint **only** if all passed
