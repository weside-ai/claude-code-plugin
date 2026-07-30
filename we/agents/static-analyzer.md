---
name: static-analyzer
description: Static code analysis — linting, formatting, types, dead code, complexity. Auto-detects project stack. Use for code quality checks before tests.
color: purple
---

# Static Code Analyzer

**Purpose:** Run ALL static analysis checks. Run this FIRST, tests SECOND.

---

## Critical Rules

1. **Run each command once** — a repeated check is noise, not confirmation
2. **Auto-fix first** — try `--fix` before reporting a failure
3. **Sequential** — checks in order, progress reported after each

---

## Step 1: Determine Scope

The changed files against the merge base. **Derive the base, never assume `main`** — the PR's
`baseRefName`, else the remote's `HEAD` symref; fall back to the last few commits when neither
resolves (detached, base not fetched).

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

Refresh dependencies with the repo's own lockfile-respecting command before checking — a lint
failure from a stale env is a false finding. Skip when the env is demonstrably current.

## Step 4: Run Checks

For each detected stack, run checks **sequentially, once each**. On a failure, run the stack's
auto-fix (`ruff check --fix` / `eslint --fix` / `prettier --write` / equivalent) and re-check.
Report status per category: "Lint: PASS", "Types: 2 errors".

## Step 5: Save Checkpoint

Extract the ticket key from the branch name into `$TICKET`, then write:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint "$TICKET" static_analysis_passed
```

**Only if ALL checks passed.** No ticket key in the branch → skip the checkpoint, report normally.

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
