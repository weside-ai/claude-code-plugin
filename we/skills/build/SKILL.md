---
name: build
description: >
  Build Orchestrator — autonomous pipeline from git preparation through
  develop, AC gate, quality gates, docs, PR, and CI review, with
  checkpoints, circuit breaker, resume. Use when the user says
  "/we:build", "implement", "build the ticket", or provides a ticket key.
---


# Build Orchestrator

You orchestrate the entire development pipeline in a single skill invocation — from git preparation through PR creation and CI review. You do NOT stop mid-pipeline.

**After every sub-skill returns, IMMEDIATELY continue with the next step.**

> **APO altitude:** Build. The plan was produced upstream by `/we:story` (Solo, Story altitude) or by `/we:meet story` for contentious stories. Build has no Solo/Meet split — there is one mode, autonomous. See [`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md) for the full altitude map.
>
> **Internal CLI back-compat:** the orchestration CLI (`scripts/orchestration.py story status|checkpoint|resume`) and the SQLite schema still use `story` as the table/command name. The Build skill is the public surface; the internal state machine keeps its existing name so checkpoints from pre-v2.28.0 sessions still resume cleanly.

---

## Execution Is Not Negotiable

By the time `/we:build` runs, the plan already exists (`/we:story` produced it — or `/we:meet story` for contentious ones) and the user has chosen to execute it. The pipeline IS the execution path, not a discovery path. The phases in the plan ARE the phase-by-phase execution — running them sequentially with checkpoints is what "phased" means here.

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
Read("${CLAUDE_PLUGIN_ROOT}/quality/dor.md")
Read("${CLAUDE_PLUGIN_ROOT}/quality/dod.md")
```

**Repo-local DoR/DoD additions (additive, optional):** resolve the repo root (`git rev-parse --show-toplevel`) and check for `<repo-root>/.weside/dor.md` and `<repo-root>/.weside/dod.md`. Read whichever exist and treat their items as ADDITIVE to the plugin defaults above — both the plugin checklist and the repo checklist apply, the repo files never replace the plugin defaults. Missing file(s) → silently proceed with the plugin defaults only.

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

Single source of truth — step, what it does, checkpoint written, who writes it. Earlier `refined` checkpoint comes from `/we:story` (Solo) before this skill is invoked.

| Step | What | Checkpoint written | Written by |
|---|---|---|---|
| 0 | Check for resume | — | — |
| 1 | DoR + load story + plan + worktree + ticket → "In Progress" | `git_prepared` | build (Step 1) |
| 2 | Develop (inline or parallel-subagent dispatch) | `implementation_complete` | build (Step 2) |
| 3 | AC verification gate (BLOCKING) | `ac_verified` | build (Step 3) |
| 4 | Simplify | `simplified` | build (Step 4) |
| 5 | PARALLEL: `/we:review` + `/we:static` + `/we:test` | `review_passed`, `static_analysis_passed`, `test_passed` | reviewer, static-analyzer, test-runner |
| 6 | Documentation check (`doc-architect`) | `docs_updated` | docs (Step 6) |
| 7 | `/we:pr` (verifies all 3 quality-gate checkpoints first) | `pr_created` | pr-creator |
| 8 | Wait for CI/reviews → ONE ci-review pass INLINE → wait → report | `ci_passed` | build (Step 8) |
| 9 | Verify ticket → "In Review" (and leave it there) | — | — |

---

## Step 0: Check for Resume

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story resume {TICKET}
```

If interrupted → ask user whether to resume from last checkpoint.

## Step 1: DoR + Load Story + Reality Check

**Resolve repo root** (do this once and reuse throughout):

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
```

Load story from ticketing tool. Verify DoR: User Story, Plan exists (`${REPO_ROOT}/docs/plans/{TICKET}-story.md` — prefer `{TICKET}-story.md`; fall back to legacy `{TICKET}-plan.md` if the new-suffix file is absent).

**Plan Completeness Gate (3-item scan):** After confirming the plan file exists, scan it for completeness before loading architecture context or creating the worktree. This is a hard gate — an incomplete plan means the story was never properly refined and `/we:build` cannot produce correct output. The gate checks the plugin DoR; if `<repo-root>/.weside/dor.md` exists (see Prerequisites above), its items apply too — the plan must satisfy plugin DoR ∪ repo DoR, not plugin DoR alone.

Check all three:

1. **ACs present and structured:** the plan contains at least one occurrence of `Given` AND `When` AND `Then` (GWT acceptance-criteria tokens). A plan with no GWT ACs hasn't been accepted as DoR-complete.
2. **Context section non-empty:** the plan has a Context section with > 50 characters of actual content (not just a header).
3. **Phase headers present:** at least one `### Phase \d+:` header exists (regex: `^### Phase [0-9]+:`).

**On failure:** stop the pipeline immediately with a specific message:

```
Plan at `${REPO_ROOT}/docs/plans/{TICKET}-story.md` is incomplete: missing <ACs|Context|Phase headers>.
Run `/we:story {TICKET}` to complete it before `/we:build`.
See ${CLAUDE_PLUGIN_ROOT}/quality/dor.md for the full DoR checklist.
```

Name the specific missing item(s). Do NOT proceed with an incomplete plan.

**CRITICAL: Always read files COMPLETELY** (no offset/limit). Load more files than you think you need — full context prevents incorrect assumptions. Never skim or partially read source files.

**Glossary:** If `CONTEXT.md` exists at the repo root, load it alongside the plan and use its canonical vocabulary.

**Architecture Context (TurboVault):** After loading the plan, use TurboVault MCP
(if available) to surface related architecture docs:
```
mcp__turbovault__find_similar_notes("${REPO_ROOT}/docs/plans/{TICKET}-story.md")
```
Read the top 3 results — they contain patterns, primitives, and ADRs relevant
to this story. Keep them in mind during implementation. If TurboVault is
unavailable, skip this lookup and note it once: "⚠️ TurboVault unavailable —
skipping architecture-context lookup; rely on the plan + code reading."

**Reality Check:** If plan exists, check creation date against recent git changes. If code changed significantly since the plan was written (files moved, APIs renamed, dependencies changed), **STOP the pipeline** and ask the user: "The plan may be outdated — key files have changed since it was written. Run `/we:story {TICKET}` to update the plan before continuing?" Do NOT proceed with a stale plan.

**Dynamic Todo-Liste:** Extract phases from plan (`### Phase \d+:` headers). Build todos for plan phases + AC Verification + Quality Gates + PR + Reviews.

**Plan Frontmatter — parse `parallel_groups`:** After loading the plan, extract the `parallel_groups` field from YAML frontmatter. Default (no field present) = all phases run sequentially inline. If present, the value is a list of lists of phase numbers — e.g. `parallel_groups: [[2,3]]` means phases 2 and 3 can run concurrently. Pass this to Step 2 to guide dispatch decisions. A phase not mentioned in any group always runs inline in plan order.

### Worktree (Default)

**Unless the user explicitly says otherwise**, create a git worktree for isolated development:

```
EnterWorktree(name="{type}/{TICKET}-short-description")
```

This gives the story an isolated copy of the repo. The worktree is kept on completion (user decides cleanup). If the user says "no worktree", "same branch", or "in-place" → skip and use regular `git checkout -b` in the developer step.

**Transition ticket → "In Progress" (MANDATORY):**

Detect the ticketing tool per `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`. GitHub Issues: no status transition possible — skip silently. None: skip silently.

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

**Conflict recovery:** After a parallel group returns, run `git status` in the feature branch. If merge conflicts exist, `parallel_groups` was misconfigured — the phases were not truly disjoint. Resolve conflicts manually, commit the resolution, and note it in the PR description. Update the plan's `parallel_groups` via `/we:story` to prevent the same conflict in future runs.

**Sub-agent brief must be self-contained.** Each dispatched agent's `prompt` must include:

1. The full path to the plan (`${REPO_ROOT}/docs/plans/{TICKET}-story.md`) and which phase number it owns
2. The phase's Goal, Files, and Approach block **verbatim** from the plan
3. The ticket key, feature branch name, and absolute repo path
4. The project conventions file (`CLAUDE.md` path)
5. **Instruction:** implement the phase, commit with message `{TICKET}: phase {N} — {description}`, push to the feature branch
6. **Instruction:** follow TDD convention — write failing tests first, then implementation. Run the repo's linter/formatter (e.g. `ruff`, `eslint`, `gofmt`, `rustfmt` — whichever is present) auto-fix before committing.
7. **Instruction:** return a short report (≤200 tokens): what was done, what was deferred, any `file:line` that is unresolved

**The orchestrator retains all pipeline ownership.** Sub-agents implement + commit only. They do NOT open PRs, transition Jira, write checkpoints, make decisions outside their phase scope, or run quality gates.

**If a sub-agent reports a real blocker** (missing dependency, auth endpoint absent, etc.), record it as a ≤200-token note and decide per-phase whether to defer and continue or stop and ask the user. A sub-agent blocker is NOT a reason to bail on all remaining phases.

---

### Per-phase checks (both modes)

**Setup (once, before any phase):**

1. **Load plan** from `${REPO_ROOT}/docs/plans/{TICKET}-story.md`. Read it COMPLETELY. Re-read `parallel_groups` to confirm Mode A or B.
2. **Formulate goal**: "The user should be able to X so that Y."

**For each phase** (after it completes — inline or agent returns):

1. Follow project conventions; write tests alongside code (TDD: test first, then implementation); run auto-fix (ruff/eslint/gofmt/rustfmt — whichever tool is present in the repo); commit.
2. **Wiring Check** — if the phase introduces new data fields: verify data flows end-to-end through all layers (model → service → API → frontend → UI). Missing wiring = feature not reachable.
   - **Seed migrations: flipping a field on an EXISTING seeded row needs a FULL-row upsert or a guarded UPDATE, never a partial `{id, col}` upsert.** A partial `seed_upsert(rows=[{"id":N, "col":val}], …)` is INSERT…ON CONFLICT DO UPDATE — if the row is absent at execution time the INSERT fallback fires and violates NOT NULL. To deactivate/flip a column on a row another migration seeded, either mirror that migration's full row (all NOT NULL columns, FKs resolved in Python) or use a guarded `UPDATE … WHERE id=N`. Run a real `alembic upgrade → downgrade → upgrade` roundtrip against a DB before trusting it.
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

4. **Run local tests** — in Mode A: after each phase. In Mode B: after each inline phase completes, and once after each parallel group integrates (not per sub-agent).
5. **Write checkpoint** `implementation_complete` — once, after ALL phases complete (both inline and parallel groups)

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

> `/we:build` is the **solo fast path** for a single Story (one Claude session, inline or parallel sub-agents). For multi-chunk work with foreign engines or Codex workers, use `/we:orchestrate` + `/we:develop` instead.

**Gates run in parallel.** Launch them in a **single message** so they execute concurrently:

- **static-analyzer** — Lint, format, types
- **test-runner** — Tests + coverage
- **Local reviewers** — driven by config + the story's intensity (below)

**Which local reviewers run (config-driven):** read `review.available` (ordered list) from
`.weside/config.json` and the story's `review_intensity` frontmatter (default `standard` if
absent). Take the **locally-invokable** entries of `review.available` in order — `claude` (the
`code-reviewer` agent) and `codex` (`/codex:review`) — and select the first N by intensity:
`light`=1, `standard`=2, `deep`=all-local. CI-only ids (`coderabbit`/`greptile`/custom bots) are
ignored here — they run on GitHub, not locally. (Note: with the default two local ids `claude`+`codex`,
`standard` and `deep` coincide until a third local reviewer exists — that's expected.)

- For each selected `claude` → launch the `code-reviewer` agent (AC-alignment + review).
- For each selected `codex` → locate the codex companion script and run it via Bash (codex is `disable-model-invocation`, so call the script, don't `Skill()` it). The script ships in the codex plugin's cache, NOT under `${CLAUDE_PLUGIN_ROOT}` (that points at the `we` plugin while build runs). Resolve it by glob and take the newest:
  ```bash
  CODEX_REVIEW=$(ls -t ~/.claude/plugins/cache/*/codex/*/scripts/codex-companion.mjs 2>/dev/null | head -1)
  if [ -n "$CODEX_REVIEW" ]; then node "$CODEX_REVIEW" review --wait; else echo "codex selected but plugin not installed — skipping"; fi
  ```
  **Skip silently with a one-line note** if `codex` is not in `review.available` OR the glob finds nothing (codex plugin not installed).
- **No `review` block in config** → fall back to today's behaviour: run the `code-reviewer` agent only.

**Cross-review hook (`review.cross`):** after local quality gates return, read `review.cross`
from `.weside/config.json` (default `true`). When `true`:
- Claude wrote this code → run `/codex:adversarial-review` as an additional review pass
  (only when `tools.codex: true`; skip with one-line note if absent)
- If workers were dispatched via a foreign engine or Codex → run the `code-reviewer` agent

For `/we:build` (solo path), the writer is always Claude, so the cross-review is
`/codex:adversarial-review` when `tools.codex` is true. Run it concurrently with the
other quality gates. When `review.cross` is false or Codex is absent, skip.

**AI CI reviewers run on GitHub, not locally.** Whatever bots the repo's `review.available`
lists as CI ids (e.g. CodeRabbit) plus Claude Review post resolvable threads + their own check
gates after PR creation. The GitHub review has better context (PR diff, commit history,
prior reviews) and is the authoritative gate. If no GitHub remote or no AI reviewer is
present, skip Steps 8d–8e (thread resolution) and treat local quality gates as authoritative.

**Wait for ALL THREE.** Then verify checkpoints:
- `review_passed` (code-reviewer clean)
- `static_analysis_passed` (static-analyzer clean)
- `test_passed` (tests green; coverage met if a coverage tool is configured — unmeasured if absent)

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
4. If any bypass annotation changed → also run (if the script exists):
   ```bash
   if [ -f "${REPO_ROOT}/scripts/generate-bypass-register.sh" ]; then
     bash "${REPO_ROOT}/scripts/generate-bypass-register.sh" --write
   fi
   ```
   Commit the regenerated register in the same docs commit (skip silently if the script is absent)
5. Commit the doc changes and write checkpoint `docs_updated`

If the agent returns "nothing needs updating" — write `docs_updated` immediately
and continue. Do not invent work.

## Step 7: PR

**BLOCKING:** Verify ALL THREE quality gate checkpoints exist before creating PR:
- `review_passed` (code review clean)
- `static_analysis_passed` (lint/format/types clean)
- `test_passed` (tests green; coverage met if measured)

If any is missing → go back to Step 5 and fix. **NEVER create a PR with failing gates.**

AI code reviewers run on GitHub after PR creation. `/we:ci-review` handles thread resolution across all of them. If no GitHub remote is configured, skip the review-thread steps — local gates are authoritative.

Call PR creator agent:

```
Agent(subagent_type="we:pr-creator", prompt="Create PR for {TICKET}")
```

Extract PR number. Write checkpoint `pr_created`.

## Step 8: ONE ci-review pass — start early, hold the push for CI (INLINE — do NOT dispatch Skill)

⛔ **Do NOT call `Skill(skill="ci-review")`!** Execute the CI-review logic inline.

**This step runs exactly ONE ci-review pass and then stops — it is not a multi-cycle loop.** The
shape preserves the early-start optimization (Phase 1b of the ci-review skill) AND guarantees the
long CI is actually checked:

- **Start as soon as the fast reviewers have posted** — do NOT wait for the long backend CI to begin
  collecting. The AI reviewers (Claude Review, CodeRabbit) post within a minute or two; start
  triaging and fixing their findings while the backend CI is still `in_progress`.
- **Hold the push until the long CI has a conclusion.** This is the only thing gated on the slow CI:
  before pushing, wait until `gh pr checks {PR}` shows no `pending`/`in_progress` left, fold any CI
  failures into the SAME fix-commit, and push once. That way review-fixes and CI-fixes ship in one
  push, not two — and the build never "ends at the PR" with CI unchecked.

**Precheck — GitHub availability:**
```bash
gh auth status 2>/dev/null && HAS_GH=1 || HAS_GH=0
```
If `HAS_GH=0`: skip the GitHub-dependent steps below. Write `ci_passed` after local quality gates pass and continue to Step 9.

When `HAS_GH=1`:

1. **Collect early** from the sources already available — all unresolved review threads + each bot's latest review body (every AI reviewer in `review.available`, e.g. CodeRabbit, plus Claude Review). Do NOT block on the long CI to start.
2. **Triage + fix** per the severity policy: BLOCKING + WARNING = must fix (unless reviewer factually wrong), SUGGESTION/NITPICK = do or consciously skip with reason. Accumulate all fixes — do NOT commit/push between them.
3. **Wait for the long CI to conclude** (`gh pr checks {PR}` until no `pending`/`in_progress`). Collect any CI failures and fold their fixes into the same set.
4. **If 0 findings total** (reviews clean AND CI green) → write checkpoint `ci_passed`, continue to Step 9.
5. **Commit** all fixes as ONE commit.
6. **Resolve** every bot-authored thread via GraphQL (the once-forgotten, now-unconditional step), verify 0 unresolved bot threads; never auto-resolve human threads.
7. **Push** once — only now, after CI concluded and all bot threads resolved.
8. **Wait for the post-push CI to settle**, then report the resulting CI state (green/red) and **STOP**.

**One pass only — then stop.** Do NOT re-enter a fix loop. After this single pass, hand back to the
user with the PR open and the ticket in "In Review" (Step 9). If the post-push CI is still red, report
it and stop — the user decides whether to run `/we:ci-review {PR}` again. Re-running the whole pass
automatically (the old "max 3 cycles") is removed.

After the pass → write checkpoint `ci_passed`.

## Step 9: Verify Ticket Transition (leave it in "In Review")

The transition to "In Review" is performed by the `pr-creator` agent in its Step 7 (see `agents/pr-creator.md`). This step runs **after** the Step 8 ci-review pass, so it is the final word on ticket state.

**Verify** the ticket actually moved to "In Review". If the ticketing tool reports the ticket is still in "In Progress" (or equivalent), retry the transition once. This is mandatory, not best-effort — the ticket MUST end the run in "In Review". Soft-fail (log a loud warning) only if the transition is genuinely rejected by the workflow/permissions after the retry.

**Leave it there.** Do not move the ticket past "In Review" — never to "Done" (that's the user's job after merge). The Step 8 fix-commit must not bounce the ticket back to "In Progress"; if your ticketing workflow auto-reopens on push, transition it back to "In Review" here.

---

## Error Handling

**Circuit Breaker:** After 3 failures in same phase → stop, present options to user.
**Resume:** On next `/we:build {TICKET}` → detect interrupted state, offer resume.

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
- Never re-invoke `Skill(skill="build")` — if you're reading this, you ARE the build skill
- Never call `Skill(skill="develop")` or `Skill(skill="ci-review")` — `Skill()` loads into the main context and inflates it. Use `Agent(subagent_type=...)` for parallel-safe phases in Step 2 (isolated context, short report back) or execute inline; Step 8 uses inline CI-review logic. Only `Skill()` dispatch is banned — `Agent()` is explicitly the correct tool for Mode B.
- Never commit code changes without corresponding test changes in the same commit
- Never create a PR before ALL THREE quality gates pass (review + static + test)
