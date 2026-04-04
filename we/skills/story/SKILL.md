---
name: story
description: >
  Story Orchestrator — coordinates the complete development pipeline from git
  preparation through PR creation and CI review. Loads plan, manages checkpoints,
  circuit breaker, and resume capability. Use when user says "/we:story",
  "implement story", or provides a ticket key.
---

# Story Orchestrator

You orchestrate the entire development pipeline in a single skill invocation — from git preparation through PR creation and CI review. You do NOT stop mid-pipeline.

**After every sub-skill returns, IMMEDIATELY continue with the next step.**

---

## Prerequisites

```
Read("quality/dor.md")
Read("quality/dod.md")
```

---

## Orchestration CLI

```bash
# Checkpoints
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story status {TICKET}
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} {phase}
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story resume {TICKET}

# Circuit breaker (3 failures → stop)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py circuit check {TICKET} {phase}
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py circuit fail {TICKET} {phase} --error "msg"
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py circuit success {TICKET} {phase}

# CI-fix loop (max 3 cycles)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py cifix start {TICKET} {pr_number}
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py cifix attempt {TICKET} {fix_type}
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py cifix success {TICKET}
```

**DB location:** `~/.claude/weside/orchestration.db` — Never access directly, always use CLI.

**Phases:** refined → git_prepared → implementation_complete → ac_verified → simplified → docs_updated → review_passed → static_analysis_passed → test_passed → pr_created → ci_passed

---

## Pipeline

```
/we:story {TICKET}
  ├── Step 0: Check for Resume
  ├── Step 1: Check DoR + Load Story + Plan (Reality Check)
  ├── Step 2: /we:develop (developer skill)
  ├── Step 3: AC Verification Gate (BLOCKING)
  ├── Step 4: Simplify
  ├── Step 5: PARALLEL: /we:review + /we:static + /we:test [+ coderabbit]
  ├── Step 6: Documentation check
  ├── Step 7: /we:pr (checks test_passed)
  ├── Step 8: Review-Fix Loop (max 3 cycles)
  └── Step 9: Ticket → In Review
```

---

## Step 0: Check for Resume

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story resume {TICKET}
```

If interrupted → ask user whether to resume from last checkpoint.

## Step 1: DoR + Load Story + Reality Check

Load story from ticketing tool. Verify DoR: User Story, Plan exists (`docs/plans/{TICKET}-plan.md`).

**CRITICAL: Always read files COMPLETELY** (no offset/limit). Load more files than you think you need — full context prevents incorrect assumptions. Never skim or partially read source files.

**Reality Check:** If plan exists, check creation date against recent git changes. Warn if code changed significantly since plan was written.

**Dynamic Todo-Liste:** Extract phases from plan (`### Phase \d+:` headers). Build todos for plan phases + AC Verification + Quality Gates + PR + Reviews.

### Worktree (Default)

**Unless the user explicitly says otherwise**, create a git worktree for isolated development:

```
EnterWorktree(name="{type}/{TICKET}-short-description")
```

This gives the story an isolated copy of the repo. The worktree is kept on completion (user decides cleanup). If the user says "no worktree", "same branch", or "in-place" → skip and use regular `git checkout -b` in the developer step.

Move ticket to "In Progress". Write checkpoint `git_prepared`.

## Step 2: Develop

Check circuit breaker, then call developer skill:

```
Skill(skill="develop", args="{TICKET}")
```

After developer returns, verify checkpoints `git_prepared` and `implementation_complete` exist. Record circuit success. **Continue immediately to Step 3.**

## Step 3: AC Verification Gate (BLOCKING)

Your responsibility — not the developer's. Fresh-load plan and story. Verify EVERY AC with concrete evidence (file path, test name, commit).

Check end-to-end: Is the feature reachable? Does the complete user flow work?

Only write checkpoint `ac_verified` when ALL items pass. If items fail → call developer again.

## Step 4: Simplify

Check `ac_verified` exists. Run `/simplify` skill (from code-simplifier plugin). If code-simplifier plugin is not installed, skip with warning: "code-simplifier plugin not available — skipping simplification. Install with: `/install code-simplifier@claude-plugins-official`". If changes made → commit. Write checkpoint `simplified`.

## Step 5: Quality Gates (PARALLEL)

Launch all agents with `run_in_background=True` in a single message:

- **code-reviewer** — Code review + AC-alignment
- **static-analyzer** — Lint, format, types
- **test-runner** — Tests + coverage
- **CodeRabbit CLI** (optional) — If `coderabbit` command available: `coderabbit review --plain --base origin/main`

Wait for all. Verify checkpoints: `review_passed`, `static_analysis_passed`, `test_passed`. If any fail → fix and re-run. Circuit breaker opens after 3 failures.

## Step 6: Documentation (/we:docs)

**Always run.** Launch the doc-manager agent to auto-detect and update affected documentation:

```
Agent(
    subagent_type="we:doc-manager",
    description="Update documentation for {TICKET}",
    prompt="Update documentation for the changes in {TICKET}. Context: [summarize what changed]",
    run_in_background=True
)
```

Wait for completion. If docs were updated → commit. Write checkpoint `docs_updated`.

## Step 7: PR

Verify `test_passed` checkpoint. Call PR creator:

```
Skill(skill="pr-creator")
```

Extract PR number. Write checkpoint `pr_created`.

## Step 8: Review-Fix Loop

Delegate to ci-review skill:

```
Skill(skill="ci-review")
```

It collects from all sources, triages, batch-fixes, resolves threads, pushes. Max 3 cycles. After reviews green → write checkpoint `ci_passed`.

## Step 9: Ticket Transition

Move ticket to "In Review". Never move to "Done" — that's the user's job.

---

## Checkpoints

| After | Phase | Written By |
|---|---|---|
| Branch + Story loaded | `git_prepared` | develop |
| Code complete | `implementation_complete` | develop |
| ACs verified | `ac_verified` | story |
| Simplified | `simplified` | story |
| Docs updated | `docs_updated` | docs |
| Review passed | `review_passed` | review |
| Static passed | `static_analysis_passed` | static |
| Tests passed | `test_passed` | test |
| PR created | `pr_created` | pr-creator |
| CI green | `ci_passed` | story |

---

## Error Handling

**Circuit Breaker:** After 3 failures in same phase → stop, present options to user.
**Resume:** On next `/we:story {TICKET}` → detect interrupted state, offer resume.

---

## Rules

- Always create todo-list before starting
- Always check DoR and load plan first
- Always use `EnterWorktree` for isolation (unless user opts out)
- Always save checkpoints after each phase
- Always run quality gates before creating PR
- Never skip test quality gate
- Never create PR if tests fail
- Never move ticket to "Done" — user's job
- Never stop mid-pipeline unless circuit breaker opens
