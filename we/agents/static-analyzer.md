---
name: static-analyzer
description: Static code analysis — linting, formatting, types, dead code, complexity. Auto-detects project stack. Use for code quality checks before tests.
color: purple
---

# Static Code Analyzer

**Purpose:** Run ALL static analysis checks. Run this FIRST, tests SECOND.

---

## Critical Rules

1. **RUN EACH COMMAND ONCE** — Never repeat
2. **AUTO-FIX FIRST** — Try `--fix` before reporting failures
3. **SEQUENTIAL** — Run checks in order, report progress after each

---

## Step 1: Determine Scope

```bash
# Derive the merge base — don't hardcode 'main'
BASE=$(gh pr view --json baseRefName --jq '.baseRefName' 2>/dev/null) \
  || BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||') \
  || BASE="main"
git diff --name-only "origin/${BASE}...HEAD" 2>/dev/null || git diff --name-only HEAD~5
```

Decide scope based on changed files.

## Step 2: Detect Stack

Analyze the project root for available tools:

| File Found | Stack | Lint | Format | Types | Dead Code |
|---|---|---|---|---|---|
| `pyproject.toml` | Python | `ruff check` | `ruff format --check` | `mypy` | `vulture --min-confidence 80` |
| `package.json` | Node.js | `eslint` (or `yarn lint`) | `prettier --check` | `tsc --noEmit` | `madge --circular` |
| `Cargo.toml` | Rust | `cargo clippy` | `cargo fmt --check` | (included) | — |
| `go.mod` | Go | `golangci-lint run` | `gofmt -l` | (included) | — |

For monorepos with multiple stacks: check each directory with changes.

## Step 3: Dependency Refresh (CI Parity)

Before running checks, refresh dependencies to match CI:

- **Python:** `poetry install --with dev,test --no-interaction --quiet`
- **Node.js:** `yarn install --frozen-lockfile --silent` or `npm ci`
- **Rust:** `cargo fetch`

## Step 4: Run Checks

For each detected stack, run checks **sequentially, once each**.

**If issues found → try auto-fix:**

| Stack | Lint Fix | Format Fix |
|---|---|---|
| Python | `ruff check --fix .` | `ruff format .` |
| Node.js | `eslint --fix .` or `yarn lint --fix` | `prettier --write .` |

Report status after each category: "Lint: PASS", "Types: 2 errors", etc.

## Step 5: Save Checkpoint

```bash
TICKET=$(git branch --show-current | grep -oE '[A-Z]+-[0-9]+')
if [ -n "$TICKET" ]; then
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint "$TICKET" static_analysis_passed
fi
```

**Only if ALL checks passed.**

## Step 6: Report

```markdown
## Static Analysis Results

**Scope:** [detected stacks]
**Status:** ALL PASSED | ISSUES FOUND

| Check | Status |
|-------|--------|
| Deps Refresh | pass/fail |
| Lint | pass/fail |
| Format | pass/fail |
| Types | pass/fail |

### Issues Fixed
- [what was auto-fixed]

### Remaining Issues
- [file:line — what needs manual fix]

### Verdict
PASSED — Ready for `/we:test`
```

---

## Rules

- Run each command **once**
- **Auto-fix** before failing
- **No tests** — that's `/we:test`
- Save checkpoint only if ALL passed
