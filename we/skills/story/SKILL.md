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
  ├── Step 2: Develop (INLINE, not Skill dispatch)
  ├── Step 3: AC Verification Gate (BLOCKING)
  ├── Step 4: Simplify
  ├── Step 5: PARALLEL: /we:review + /we:static + /we:test [+ coderabbit]
  ├── Step 6: Documentation check
  ├── Step 7: /we:pr (checks test_passed)
  ├── Step 8: Review-Fix Loop (INLINE, max 3 cycles)
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

**Architecture Context (TurboVault):** After loading the plan, use TurboVault MCP
(if available) to surface related architecture docs:
```
mcp__turbovault__find_similar_notes("docs/plans/{TICKET}-plan.md")
```
Read the top 3 results — they contain patterns, primitives, and ADRs relevant
to this story. Keep them in mind during implementation.

**Reality Check:** If plan exists, check creation date against recent git changes. If code changed significantly since the plan was written (files moved, APIs renamed, dependencies changed), **STOP the pipeline** and ask the user: "The plan may be outdated — key files have changed since it was written. Run `/we:refine {TICKET}` to update the plan before continuing?" Do NOT proceed with a stale plan.

**Dynamic Todo-Liste:** Extract phases from plan (`### Phase \d+:` headers). Build todos for plan phases + AC Verification + Quality Gates + PR + Reviews.

### Worktree (Default)

**Unless the user explicitly says otherwise**, create a git worktree for isolated development:

```
EnterWorktree(name="{type}/{TICKET}-short-description")
```

This gives the story an isolated copy of the repo. The worktree is kept on completion (user decides cleanup). If the user says "no worktree", "same branch", or "in-place" → skip and use regular `git checkout -b` in the developer step.

Move ticket to "In Progress". Write checkpoint `git_prepared`.

## Step 2: Develop (INLINE — do NOT dispatch Skill)

⛔ **Do NOT call `Skill(skill="develop")`!** Skill() expands context and causes the orchestrator to lose control after the developer finishes. Instead, execute development steps inline.

Check circuit breaker. Then implement directly:

1. **Load plan** from `docs/plans/{TICKET}-plan.md`. Read it COMPLETELY.
2. **Formulate goal**: "The user should be able to X so that Y."
3. **Implement phase by phase** from plan. For each phase:
   - Follow project conventions
   - Write tests alongside code (TDD: test first, then implementation)
   - Run auto-fix (ruff/eslint) after each phase
   - Commit after each phase
4. **Wiring Check** after each phase that introduces new data fields: verify data flows end-to-end through all layers (model → service → API → frontend → UI). Missing wiring = feature not reachable.
5. **Security Check** — if code touches auth, external APIs, user data, or file uploads:

   | Check | What to Verify |
   |-------|---------------|
   | Authentication | New endpoints require authentication |
   | Authorization | Data access scoped to current user/tenant |
   | Input validation | All external input validated at boundaries |
   | Error messages | No internal details leaked (generic errors only) |
   | SQL/NoSQL | Parameterized queries only (no string concatenation) |
   | Secrets | No hardcoded credentials, tokens, or API keys |
   | Rate limiting | Expensive endpoints have rate limits |

6. **Run local tests** before marking complete
7. **Write checkpoint** `implementation_complete`

**3 Guiding Questions (check after each phase):**
- "Can the user use the feature NOW?"
- "Is the feature REACHABLE?"
- "Does this bring me closer to the Story GOAL?"

**Continue immediately to Step 3.**

## Step 3: AC Verification Gate (BLOCKING)

Fresh-load plan and story. Verify EVERY AC with concrete evidence (file path, test name, commit).

Check end-to-end: Is the feature reachable? Does the complete user flow work?

Only write checkpoint `ac_verified` when ALL items pass. If items fail → go back to Step 2 and fix.

## Step 4: Simplify

Check `ac_verified` exists. Run `/simplify` skill (from code-simplifier plugin). If code-simplifier plugin is not installed, skip with warning: "code-simplifier plugin not available — skipping simplification. Install with: `/install code-simplifier@claude-plugins-official`". If changes made → commit. Write checkpoint `simplified`.

## Step 5: Quality Gates (PARALLEL)

**Four gates run in parallel.** Launch them in a **single message** so they execute concurrently:

**5a. Three subagents via `Agent(run_in_background=True)`:**

- **code-reviewer** — Code review + AC-alignment
- **static-analyzer** — Lint, format, types
- **test-runner** — Tests + coverage

**5b. CodeRabbit CLI via `Bash(run_in_background=True)`:**

In the **same message** as the three `Agent()` calls, also start:

```
Bash(
    command="command -v coderabbit >/dev/null 2>&1 && coderabbit review --plain --base origin/main || echo 'CODERABBIT_MISSING'",
    run_in_background=True,
    description="CodeRabbit local review"
)
```

**CodeRabbit is mandatory, not optional.** If the command returns `CODERABBIT_MISSING`:
- **STOP the pipeline.** Do not continue to Step 6.
- Tell the user: *"CodeRabbit CLI not found. Install with `curl -fsSL https://cli.coderabbit.ai/install.sh | sh` and re-run `/we:story`. Missing CodeRabbit is a setup bug, not an acceptable skip."*
- Do NOT write the `coderabbit_passed` checkpoint.

**Triage CodeRabbit findings** using the same severity mapping as `/we:ci-review`:
- **BLOCKING** = CRITICAL / MAJOR → must fix before continuing
- **WARNING** = MINOR → fix unless factually wrong
- **INFO** = NITPICK / Suggestions → evaluate, document if skipped

**Wait for ALL FOUR.** Then verify checkpoints:
- `review_passed` (code-reviewer clean)
- `static_analysis_passed` (static-analyzer clean)
- `test_passed` (tests green + coverage met)
- `coderabbit_passed` (0 BLOCKING findings; WARNINGs fixed or factually justified)

If any fail → fix and re-run. Circuit breaker opens after 3 failures.

## Step 6: Documentation (/we:docs — doc-architect)

**Always run.** Launch the `doc-architect` agent (via `/we:docs`) to read the
doc landscape fresh, identify what needs updating for this story's diff, and
propose concrete doc changes.

The agent reads rules, indices (`PRIMITIVES.md`, `foundations/README.md`,
`adr/README.md`), and the tree at boot — it does NOT rely on a cached doc
map. It never writes autonomously — every change is a diff proposal.

```
Agent(
    subagent_type="we:doc-architect",
    description="Update documentation for {TICKET}",
    prompt="Story {TICKET} is implemented. Git diff between this branch and main: <summary of what changed>. Running in proactive mode: what documentation needs updating? Return a concise list of proposed doc updates (file, change, why). If nothing needs updating, say so explicitly.",
    run_in_background=True
)
```

When the agent returns with proposals:

1. Present them to the user (concise list — the agent already formatted it)
2. User approves / adjusts / rejects each proposal
3. On approval → apply the diffs via Edit
4. If any bypass annotation changed → also run
   `bash scripts/generate-bypass-register.sh --write` and commit the
   regenerated register in the same docs commit
5. Commit the doc changes and write checkpoint `docs_updated`

If the agent returns "nothing needs updating" — write `docs_updated` immediately
and continue. Do not invent work.

**Note on the legacy `doc-manager` agent:** it is deprecated and now a thin
delegate to `doc-architect`. Existing call sites still work but new code
should invoke `we:doc-architect` directly.

## Step 7: PR

**BLOCKING:** Verify ALL FOUR quality gate checkpoints exist before creating PR:
- `review_passed` (code review clean)
- `static_analysis_passed` (lint/format/types clean)
- `test_passed` (tests green + coverage met)
- `coderabbit_passed` (local CodeRabbit clean — 0 BLOCKING findings)

If any is missing → go back to Step 5 and fix. **NEVER create a PR with failing gates.**

Call PR creator agent:

```
Agent(subagent_type="we:pr-creator", prompt="Create PR for {TICKET}")
```

Extract PR number. Write checkpoint `pr_created`.

## Step 8: Review-Fix Loop (INLINE — do NOT dispatch Skill)

⛔ **Do NOT call `Skill(skill="ci-review")`!** Execute CI-review steps inline:

1. **Collect** findings from CI, Claude Review, and CodeRabbit (use `gh` CLI)
2. **Triage**: BLOCKING = must fix, WARNING = fix unless wrong, INFO = evaluate
3. **If 0 findings** → write checkpoint `ci_passed`, continue to Step 9
4. **Batch fix** all issues locally, ONE commit with all fixes
5. **Resolve** CodeRabbit threads via GraphQL, verify 0 unresolved
6. **Push** only when all threads resolved
7. **Repeat** (max 3 cycles). After 3 → stop, ask user.

After reviews green → write checkpoint `ci_passed`.

## Step 9: Verify Ticket Transition

The transition to "In Review" is performed by the `pr-creator` agent in its Step 7 (see `agents/pr-creator.md`).

**Verify** the ticket actually moved. If the ticketing tool reports the ticket is still in "In Progress" (or equivalent), retry the transition once. Never move to "Done" — that's the user's job.

---

## Checkpoints

| After | Phase | Written By |
|---|---|---|
| Branch + Story loaded | `git_prepared` | story (Step 1) |
| Code complete | `implementation_complete` | story (Step 2) |
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
- Always verify ticket is in "In Review" after PR creation — retry once if not
- Never skip test quality gate
- Never create PR if tests fail
- Never move ticket to "Done" — user's job
- Never stop mid-pipeline unless circuit breaker opens
- Never re-invoke `Skill(skill="story")` — if you're reading this, you ARE the story skill
- Never call `Skill(skill="develop")` or `Skill(skill="ci-review")` — these expand context and break the pipeline. Execute their logic INLINE in Steps 2 and 8.
- Never commit code changes without corresponding test changes in the same commit
- Never create a PR before ALL FOUR quality gates pass (review + static + test + coderabbit)
