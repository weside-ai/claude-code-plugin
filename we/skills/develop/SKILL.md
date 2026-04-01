---
name: develop
description: >
  Developer skill for implementing code. Handles branch creation, coding,
  testing, and commits. Called by /we:story orchestrator or directly via
  /we:develop. Use when user says "/we:develop" or when /we:story calls this skill.
---

# Developer

You implement features and write tests.

## 3 Guiding Questions

1. **"Can the user use the feature NOW?"** — Not just code exists, but end-to-end usable
2. **"Is the feature REACHABLE?"** — Button, route, screen, endpoint exists
3. **"Does this bring me closer to the Story GOAL?"** — Don't get lost in side work

---

## Orchestration CLI

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} {phase}
```

Full reference: `flow/orchestration.md`

---

## Steps

### 1. Git Preparation

Check if on a feature branch. If not, create one from `origin/main`:

```bash
git checkout -b feat/{TICKET}-short-description origin/main
```

Write checkpoint `git_prepared`.

### 2. Load Story + Plan

Load story from ticketing tool. Formulate the goal: "The user should be able to X so that Y."

**Enter Plan Mode** (`EnterPlanMode()`) to create a detailed implementation plan. Explore the codebase. Present plan for user approval before coding.

After approval: `ExitPlanMode()` and proceed.

### 3. Implement (Phase by Phase)

When called by `/we:story`, the orchestrator has already created phase-based todos. Work through them.

When called directly (`/we:develop`), extract phases from `docs/plans/{TICKET}-plan.md`.

For each phase:
- Follow project conventions and patterns
- Write tests alongside code
- Commit after each phase

After all phases: **check end-to-end. Can the user reach and use the feature?**

### 3b. Wiring Check

After each phase that introduces new data fields or parameters, verify the data flows end-to-end through all layers (model → service → API → frontend → UI). This is a generic check — adapt to your project's architecture.

### 3c. AC Verification (when called directly)

When called directly via `/we:develop` (without orchestrator): verify ACs yourself. Load story fresh, check every AC with evidence. If orchestrator called you → skip (orchestrator does this in Step 3).

### 4. Security Check

If your code touches auth, external APIs, user data, or file uploads:
- SQL Injection? Use ORM/parameterized queries
- Unvalidated input? Validate at boundaries
- Error messages generic? No internal details exposed
- Rate limiting on expensive endpoints?

### 5. Auto-Fix + Local Tests

Detect project stack and run appropriate tools:

| Stack | Lint Fix | Tests |
|---|---|---|
| Python | `ruff check --fix . && ruff format .` | `pytest tests/ -v --tb=short -x` |
| Node.js | `eslint --fix .` | `yarn test` or `npx vitest` |

**If test fixtures/conftest changed → run FULL suite (no `-x`).**

### 6. Final Commit + Checkpoint

Ensure `git status` is clean. Write checkpoint:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} implementation_complete
```

---

## Handoff to Orchestrator

When called by `/we:story`, after writing `implementation_complete`, output EXACTLY:

> Developer done. Orchestrator: continue with Step 3 (AC Verification).

Do NOT summarize, do NOT suggest next steps. Just the signal line.

---

## Commit Format

```
<type>(<scope>): <subject>

<body>

{TICKET}
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`

---

## Rules

- Always commit after each phase (not just at the end)
- Always run auto-fix before committing
- Always run local tests before marking complete
- Never start implementation without a plan
- When called by orchestrator: clean handoff signal, no extras
