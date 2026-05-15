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

## Execution Is Not Negotiable

By the time `/we:story` runs, the plan already exists (`/we:refine` produced it) and the user has chosen to execute it. The pipeline IS the execution path, not a discovery path. The phases in the plan ARE the phase-by-phase execution — running them sequentially with checkpoints is what "phased" means here.

**Do NOT ask the user how to run the story.** Specifically forbidden:

- **At the start:** "Should I run this end-to-end or phase by phase?" / "This story is large — how would you like to proceed?" — No. Just start. Story size and phase count are not negotiation levers; a 6-phase encryption story and a 1-phase typo fix run the same pipeline.
- **Mid-pipeline, on token-budget grounds:** "The context is getting large, should I split the PR?" / "We're approaching the token limit, want me to stop?" — No. The session runs on a 1M-token model and the runtime auto-compacts older turns. Token pressure is not your problem to solve by interrupting the user. Keep going. If compaction actually happens, the checkpoint system lets you resume — that's exactly what it's for.

**Legitimate reasons to interrupt the user (these stay — judgment is not abolished):**

1. **Circuit Breaker** — 3 failures in the same phase. Present options.
2. **AC Verification Gate** (Step 3) — blocking checkpoint by design.
3. **Plan ambiguity that blocks implementation** — a concrete, named gap in the plan that cannot be resolved by reading the code. State the gap, ask the specific question, continue.
4. **Destructive or out-of-scope action** — anything the system prompt's "executing actions with care" rules require confirmation for (force-push, dropping data, deleting branches, etc.).

If your reason to interrupt does not fit one of those four buckets, the answer is: just execute.

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

---

## Pipeline

Single source of truth — step, what it does, checkpoint written, who writes it. Earlier `refined` checkpoint comes from `/we:refine` before this skill is invoked.

| Step | What | Checkpoint written | Written by |
|---|---|---|---|
| 0 | Check for resume | — | — |
| 1 | DoR + load story + plan + worktree + ticket → "In Progress" | `git_prepared` | story (Step 1) |
| 2 | Develop (inline or parallel-subagent dispatch) | `implementation_complete` | story (Step 2) |
| 3 | AC verification gate (BLOCKING) | `ac_verified` | story (Step 3) |
| 4 | Simplify | `simplified` | story (Step 4) |
| 5 | PARALLEL: `/we:review` + `/we:static` + `/we:test` | `review_passed`, `static_analysis_passed`, `test_passed` | reviewer, static-analyzer, test-runner |
| 6 | Documentation check (`doc-architect`) | `docs_updated` | docs (Step 6) |
| 7 | `/we:pr` (verifies all 3 quality-gate checkpoints first) | `pr_created` | pr-creator |
| 8 | Review-fix loop INLINE (max 3 cycles) | `ci_passed` | story (Step 8) |
| 9 | Verify ticket → "In Review" | — | — |

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

**Plan Frontmatter — parse `parallel_groups`:** After loading the plan, extract the `parallel_groups` field from YAML frontmatter. Default (no field present) = all phases run sequentially inline. If present, the value is a list of lists of phase numbers — e.g. `parallel_groups: [[2,3]]` means phases 2 and 3 can run concurrently. Pass this to Step 2 to guide dispatch decisions. A phase not mentioned in any group always runs inline in plan order.

### Worktree (Default)

**Unless the user explicitly says otherwise**, create a git worktree for isolated development:

```
EnterWorktree(name="{type}/{TICKET}-short-description")
```

This gives the story an isolated copy of the repo. The worktree is kept on completion (user decides cleanup). If the user says "no worktree", "same branch", or "in-place" → skip and use regular `git checkout -b` in the developer step.

**Transition ticket → "In Progress" (MANDATORY):**

Detect the available ticketing tool (in priority order):
1. Atlassian MCP (`jira_*` tools) → get transitions, find "In Progress", execute transition
2. `gh` CLI → GitHub Issues (no status transition possible — skip silently)
3. Nothing → skip silently

For Jira (Atlassian MCP):
1. Get available transitions: `jira_get_issue(issue_key=TICKET, expand="transitions")`
2. Find the transition to "In Progress" (name varies: "In Progress", "Start Progress", "In Bearbeitung")
3. Execute: `jira_transition_issue(issue_key=TICKET, transition_id=...)`
4. **Verify** the ticket actually moved — re-fetch and check status. If it didn't move, retry once with a different transition name.

If transition fails → log warning and continue. Do NOT block the pipeline.

Write checkpoint `git_prepared`.

## Step 2: Develop (inline or parallel-subagent dispatch)

⛔ **Do NOT call `Skill(skill="develop")`!** `Skill()` loads a skill into the main context, inflating it and causing the orchestrator to lose control. Use one of the two modes below instead.

Check circuit breaker. Then choose mode based on the plan's `parallel_groups` frontmatter (parsed in Step 1):

---

### Mode A — Sequential inline (default)

**When:** `parallel_groups` is absent or empty (`[]`) in the plan, or the story has only one phase.

Execute all phases inline in the orchestrator thread, one after another. This is the unchanged behaviour for simple stories.

---

### Mode B — Parallel subagent dispatch

**When:** `parallel_groups` is a non-empty list in the plan frontmatter.

For each group in `parallel_groups`, dispatch one `Agent()` per phase in that group in a **single message** so they execute concurrently. Wait for all agents in the group before starting the next group or returning to inline phases.

```
# Example for parallel_groups: [[2,3]] — phases 1 and 4 are inline, 2+3 are parallel

# Phase 1 — inline (not in any group)
# implement phase 1 directly in the orchestrator thread, commit

# Group [2,3] — dispatch concurrently in ONE message:
Agent(
    subagent_type="general-purpose",
    model="sonnet",
    run_in_background=True,
    description="Implement Phase 2 of {TICKET}",
    prompt=<phase-developer brief for phase 2>
)
Agent(
    subagent_type="general-purpose",
    model="sonnet",
    run_in_background=True,
    description="Implement Phase 3 of {TICKET}",
    prompt=<phase-developer brief for phase 3>
)

# Wait for both agents to return, then check for conflicts / integrate
# Phase 4 — inline (after group completes)
# implement phase 4 directly in the orchestrator thread, commit
```

**Sub-agent brief must be self-contained.** Each dispatched agent's `prompt` must include:

1. The full path to the plan (`docs/plans/{TICKET}-plan.md`) and which phase number it owns
2. The phase's Goal, Files, and Approach block **verbatim** from the plan
3. The ticket key, feature branch name, and absolute repo path
4. The project conventions file (`CLAUDE.md` path)
5. **Instruction:** implement the phase, commit with message `{TICKET}: phase {N} — {description}`, push to the feature branch
6. **Instruction:** return a short report (≤200 tokens): what was done, what was deferred, any `file:line` that is unresolved

**The orchestrator retains all pipeline ownership.** Sub-agents implement + commit only. They do NOT open PRs, transition Jira, write checkpoints, make decisions outside their phase scope, or run quality gates.

**If a sub-agent reports a real blocker** (missing dependency, auth endpoint absent, etc.), record it as a ≤200-token note and decide per-phase whether to defer and continue or stop and ask the user. A sub-agent blocker is NOT a reason to bail on all remaining phases.

---

### Per-phase checks (both modes)

**Setup (once, before any phase):**

1. **Load plan** from `docs/plans/{TICKET}-plan.md`. Read it COMPLETELY. Re-read `parallel_groups` to confirm Mode A or B.
2. **Formulate goal**: "The user should be able to X so that Y."

**For each phase** (after it completes — inline or agent returns):

1. Follow project conventions; write tests alongside code (TDD: test first, then implementation); run auto-fix (ruff/eslint); commit.
2. **Wiring Check** — if the phase introduces new data fields: verify data flows end-to-end through all layers (model → service → API → frontend → UI). Missing wiring = feature not reachable.
3. **Security Check** — if the phase touches auth, external APIs, user data, or file uploads:

   | Check | What to Verify |
   |-------|---------------|
   | Authentication | New endpoints require authentication |
   | Authorization | Data access scoped to current user/tenant |
   | Input validation | All external input validated at boundaries |
   | Error messages | No internal details leaked (generic errors only) |
   | SQL/NoSQL | Parameterized queries only (no string concatenation) |
   | Secrets | No hardcoded credentials, tokens, or API keys |
   | Rate limiting | Expensive endpoints have rate limits |

4. **Run local tests** — in Mode A: after each phase. In Mode B: once after the full parallel group integrates (not per sub-agent), then once more after any inline phases that follow.
5. **Write checkpoint** `implementation_complete`

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

Check `ac_verified` exists. Invoke the `simplify` skill via `Skill(skill="simplify")`. Availability is verified once during `/we:setup` (Step 1b — prerequisite check); do NOT re-derive availability from plugin paths or memory here. The only legitimate skip is when the Skill tool actually returns a "skill not found" error — in that case warn `"simplify skill not available — run /we:setup to verify prerequisites"` and continue. If changes made → commit. Write checkpoint `simplified`.

## Step 5: Quality Gates (PARALLEL)

**Three gates run in parallel.** Launch them in a **single message** so they execute concurrently:

Three subagents via `Agent(run_in_background=True)`:

- **code-reviewer** — Code review + AC-alignment
- **static-analyzer** — Lint, format, types
- **test-runner** — Tests + coverage

**CodeRabbit runs on GitHub, not locally.** The `check-coderabbit` CI gate
enforces CRITICAL/MAJOR thread resolution after PR creation. Local CodeRabbit
CLI is not part of this pipeline — the GitHub review has better context
(PR diff, commit history, prior reviews) and is the authoritative gate.

**Wait for ALL THREE.** Then verify checkpoints:
- `review_passed` (code-reviewer clean)
- `static_analysis_passed` (static-analyzer clean)
- `test_passed` (tests green + coverage met)

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
    prompt="Story {TICKET} is implemented. Git diff between this branch and main: <summary of what changed>. Running in proactive mode: what documentation needs updating? Also: does this story introduce or significantly change a user-facing flow? If yes, propose creating or updating a journey doc (docs/architecture/journey-*.md). Return a concise list of proposed doc updates (file, change, why). If nothing needs updating, say so explicitly.",
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

**BLOCKING:** Verify ALL THREE quality gate checkpoints exist before creating PR:
- `review_passed` (code review clean)
- `static_analysis_passed` (lint/format/types clean)
- `test_passed` (tests green + coverage met)

If any is missing → go back to Step 5 and fix. **NEVER create a PR with failing gates.**

CodeRabbit runs on GitHub after PR creation. `/we:ci-review` handles thread resolution.

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

## Error Handling

**Circuit Breaker:** After 3 failures in same phase → stop, present options to user.
**Resume:** On next `/we:story {TICKET}` → detect interrupted state, offer resume.

---

## Rules

- Always create todo-list before starting
- Always check DoR and load plan first
- Always use `EnterWorktree` for isolation (unless user opts out)
- Always name branches with ticket key FIRST: `{type}/{TICKET}-short-description` (e.g., `feat/PROJ-123-add-login`, `fix/PROJ-456-null-pointer`). The ticket key must appear before the description so it can be extracted reliably via regex.
- Always transition ticket to "In Progress" in Step 1 — verify it moved, retry once if not
- Always save checkpoints after each phase
- Always run quality gates before creating PR
- Always verify ticket is in "In Review" after PR creation — retry once if not
- Never skip test quality gate
- Never create PR if tests fail
- Never move ticket to "Done" — user's job
- Never stop mid-pipeline unless circuit breaker opens
- Never re-invoke `Skill(skill="story")` — if you're reading this, you ARE the story skill
- Never call `Skill(skill="develop")` or `Skill(skill="ci-review")` — `Skill()` loads into the main context and inflates it. Use `Agent(subagent_type=...)` for parallel-safe phases in Step 2 (isolated context, short report back) or execute inline; Step 8 uses inline CI-review logic. Only `Skill()` dispatch is banned — `Agent()` is explicitly the correct tool for Mode B.
- Never commit code changes without corresponding test changes in the same commit
- Never create a PR before ALL THREE quality gates pass (review + static + test)
