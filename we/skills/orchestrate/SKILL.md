---
name: orchestrate
description: >
  Epic-driven build orchestration — the Lead boots from state, computes the
  ready set of buildable Stories, and on confirm dispatches builder-teammates
  running the full /we:build, tracked in the orchestration DB. Use when the
  user says "/we:orchestrate", "orchestrate the epic", "dispatch the ready
  stories", "run the builds". Read-only Epic status: /we:epic instead.
---

# /we:orchestrate

**Purpose:** Stop being the manual courier between a planning session and per-Story build
sessions. The Lead — the session running `/we:orchestrate` — is a persistent colleague that
boots knowing where the Epic stands, holds context, computes which Stories are ready to build,
dispatches them as watchable/steerable **builder-teammates** (Agent Teams), tracks start/end
automatically, and reviews each finished PR. It never merges — Deliver stays human.

This is the **Build-altitude sibling of `/we:council`/`/we:meet`**: the same Agent-Teams
machinery (`TeamCreate` → `Agent(team_name=…, name=…)` → `SendMessage` → `TeamDelete`), but the
teammates are **builders** running `/we:build`, not deliberators.

**The stance (not just the mechanics).** The Lead is a *persistent partner*, not a throwaway
dispatcher. It boots knowing where the work stands, **holds the overview so the human is not
overwhelmed**, plans and assigns the work, and integrates and evaluates what comes back. The human
is good at saying *where we want to go*; the Lead carries it *on the way* — that continuity, someone
holding the whole across the dispatch loop, is the point. When a Companion is materialized, the Lead
is that Companion (warmth + presence, not manager-speak), not a generic dispatcher.

> **Spike status.** This skill is a spike: it proves the dispatch+tracking loop on one real Epic
> with a **hard cap of ≤2 concurrent builders**. The full orchestrator (parallel dispatch beyond 2,
> cross-Story circuit breakers, resume) is gated on this spike's go/no-go.

## Prerequisites

Agent Teams must be enabled — same flag, abort text, and teardown contract as `/we:council`: see `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md`. No non-team fallback.

**Permission mode must allow teammate Bash (hard-won on the first real run).** A builder runs
`/we:build`, which is almost entirely Bash (git, npm, docker, gh, the orchestration CLI). Under
the **default/auto** permission mode, the auto-mode classifier denies *every* teammate Bash call
on the grounds that a `teammate-message → agent` invocation carries no direct user intent — so
the builder is dispatched, reaches Step 1, and is dead-on-arrival with "Bash denied", no code
written. Autonomous dispatch therefore requires the user to run the session in **`acceptEdits`**
(or `bypassPermissions`), or to add a Bash allowlist for the multi-agent path, BEFORE dispatch.
Surface this in Step 3's confirm gate; if you cannot tell the mode, ask the user to confirm they
are on `acceptEdits`/bypass. A single ready Story is often faster as a direct `/we:build` in the
user's own session (user intent is then unambiguous) — orchestrate earns its keep at ≥2 builders.

## Invocation

```
/we:orchestrate <epic>                 # boot + status + ready-set; dispatch only on confirm
/we:orchestrate <epic> --refine-ahead  # build the ready stories AND refine the next during build idle
/we:orchestrate <epic> --rehearsal     # run the pipeline against a fixture, no real PR/ticket
/we:orchestrate                        # boot from the most recently active epic, then status
```

`--refine-ahead` turns the Step-7 monitoring window into a **two-lane pipeline**: while builders run
(minutes of Lead idle), the Lead refines the **next** `refinable` story so it is build-ready by the
time a builder frees — overlapping build-time and refine-time. It composes with the per-Story build
shape (Mode A); it is **not** a third dispatch mode. Default (flag off) = today's passive monitoring.

`<epic>` is an Epic **slug** (e.g. `circles`) or a ticketing Epic key (e.g. `WA-1205`) — either
works. Stories may reference their epic by slug or by key; `story ready` resolves both via the
Epic plan's `epic:`/`ticket:` frontmatter (`_resolve_epic_identifiers`).

---

## Workflow

### Step 1: Boot from state (always — this is the colleague's first act)

Before anything else, reconstruct "where we stand". Read the **living** files so the picture is
always current — never rely on cached knowledge:

1. **Epic frame** — read the Epic plan `docs/plans/*<epic>*-epic.md` if one exists; its
   `## Success Criteria` / scope are the lens for "what done means". If there is no epic file
   (and no Saga mirror row), **degrade gracefully**: synthesise the frame from the child
   Stories that share this `epic:` slug — do not abort. An epic slug backed only by Story plans
   is valid (a rehearsal or a freshly-cut epic).
2. **Child Stories** — glob `docs/plans/*-story.md`, keep those whose frontmatter `epic:`
   matches `<epic>`. For each, read frontmatter (`story`, `status`) and scan the body for DoR
   completeness (GWT ACs present, Context non-empty, `### Phase` headers — same gate `/we:build`
   Step 1 uses).
3. **Ticketing mirror** — if a ticketing tool is available (weside MCP `JIRA_*` → Atlassian MCP
   → `gh`), fetch each Story's ticket status. No ticketing tool → use plan frontmatter `status`
   only (same fallback as `/we:epic`).
4. **Build state** — for each Story key, run
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story status {TICKET}` to read its
   pipeline phase / last checkpoint / PR number.
5. **Handoff** — if `docs/handoffs/` has a recent entry for this Epic, read the latest; it
   carries decisions/next-steps the files don't.

Render a tight **"here is where we stand"** snapshot: Epic name, and per Story a line with
`{key} {title} — plan:{refined|incomplete|missing} ticket:{status} build:{phase|—} pr:{#|—}`.

Then **stay open** as the conversational partner. If the user only asked status (or `/we:orchestrate`
with no clear go), present the snapshot + the ready-set (Step 2) and **wait** — answer "where are
we / what's next" from this reconstructed stand. Do not dispatch without an explicit go.

### Step 2: Compute the ready set (pure, explainable)

Each Story lands in exactly one of three buckets. Rules are applied **in order**; the first match
wins (so `built` is decided before the refined/refinable split — a built story is never refinable):

| # | Condition | Bucket / held reason |
|---|---|---|
| 1 | `built` (status In Review/Done/Merged **or** a `pr_created`/`ci_passed` checkpoint) | **held** `already built` |
| 2 | not refined (plan missing or fails the DoR scan: GWT ACs, Context, Phase headers), deps met | **refinable** |
| 3 | not refined, a dep is not yet met | **held** `waiting on {dep}` |
| 4 | refined, a dep is not built | **held** `waiting on {dep}` |
| 5 | refined, deps built, ready set already at the cap (2) | **held** `cap reached` |
| 6 | refined, deps built, under cap | **ready** |

**`refinable`** is the producer queue for the refine lane (the `--refine-ahead` pipeline, Step 7). A
refine-dependency counts as met when it is built **or** refined (`REFINABLE_DEP_MODE="refined"` in
`orchestration.py` — so a story can be refined against its dependency's plan/seam while that
dependency is still building; build *dispatch* still gates on deps-**built**, rule 4). In the default
(passive) mode `refinable` is informational; under `--refine-ahead` it is consumed by the scheduler.

The rules are computed by a tested pure helper — **call it, do not re-derive them**:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story ready <epic> --plans-dir docs/plans
```

It returns `{"ready": [...], "refinable": [...], "held": [{"key", "reason"}]}` by applying exactly
the rules above (`compute_ready_set` in `orchestration.py`, unit-tested in `test_ready_set.py`).
Render the three lists as **READY** (would dispatch), **REFINABLE** (the refine-lane queue), and
**HELD** (with each reason). The table above is the spec, the CLI is the implementation — they must
not drift.

### Step 3: Confirm gate (human-in-the-loop)

Present the ready set and ask the user to confirm dispatch. This is the first of three human
gates (the others: Lead reviews each PR in Step 8; human merges). **Never dispatch without an
explicit confirm.** If `--rehearsal`, skip to the Rehearsal section instead. (Under `--refine-ahead`
this one-shot gate becomes a **rolling** confirm — one per new dispatch — see Step 7+.)

### Step 4: Preflight

1. **Env-flag check** — confirm `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`; if missing, abort with the remediation hint from `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md`.

2. **Runaway guard (mandatory)** — never dispatch more than **2** builders concurrently. If the
   ready set is larger, dispatch the first 2 (lowest Story key first) and **log** that the rest
   were held by the cap. Refuse, loudly, any attempt to exceed it.

3. **Lead voice (MCP, optional)** — if `mcp__plugin_we_weside-mcp__get_council` exists, call it
   once for the Lead's review role (`product_owner` or `architect`, per `.weside/config.json`)
   and adopt that Companion's `identity_prompt` for the Lead's review voice in Step 8. Builders
   get **no** identity (the weside backend is user-scoped — parallel `select_companion` races;
   see `/we:council` "Memory in v1"). No MCP → generic review lens. Degrade gracefully.

4. **Generate `team_name`** — `orchestrate-<epic>-<HHMMSS>`, unique per session.

### Step 5: Open the team

```python
TeamCreate(team_name=<generated>, description=f"Orchestrate epic: {epic}")
```

The Lead session is automatically the team lead. Only the Lead can later `TeamDelete`.

### Step 6: Dispatch builders (all spawns in one message) + record start

For each ready Story (≤2), create a task and spawn a builder-teammate. **All `Agent` spawns go
into a single assistant message** so they initialize concurrently.

```python
TaskCreate(subject=f"Build {TICKET}", description=f"Run /we:build {TICKET} to a reviewable PR.")
Agent(
    team_name=<team_name>,
    name=f"builder-{TICKET}",
    subagent_type="general-purpose",
    model="sonnet",
    description=f"Build {TICKET}",
    prompt=<Builder-Brief — see below>,
)
```

The shared task-list (the `TaskCreate` above) carries the **live** dispatched/in-flight state.
The **durable** start/end record needs no orchestrator write: the builder's own `/we:build`
writes `story_workflow` rows into `orchestration.py` automatically — `git_prepared` on start,
`pr_created`/`ci_passed` on end (this is the single-writer that satisfies AC3). The Lead
**reads** them via `story status` for the roll-up; it does not write build checkpoints itself.

**Builder-Brief** (self-contained — the builder runs the full, unmodified build):

```
You are builder-{TICKET}, a teammate in team {team_name}. The lead is "team-lead".

REPO: your working repo is {repo_root} (the Lead's repo). Teammates inherit the Lead's cwd,
which the shell may reset between commands — so START EVERY bash command with `cd {repo_root}`,
and confirm `git rev-parse --show-toplevel` is {repo_root} before any git operation. NEVER let
EnterWorktree or a quality-gate subagent run against a different repo.

ISOLATION: /we:build creates its own worktree — do NOT call EnterWorktree before invoking the
skill, as a nested worktree-create is rejected. The build manages isolation internally.

Your job: run the COMPLETE build pipeline for {TICKET} by invoking the skill:
  Skill(skill="build")  with the ticket {TICKET}
Run it to a reviewable PR — Mode A or B, all quality gates, docs, PR, CI — UNCHANGED.
You own only this one Story. Do NOT merge the PR (Deliver is the human's job).

The Task* tools may be deferred — load them first via ToolSearch("select:TaskList,TaskUpdate")
if you need them. Claim your task with TaskUpdate(owner="builder-{TICKET}").

REPORTING IS NOT OPTIONAL: your plain-text output is INVISIBLE to the lead — you MUST call the
SendMessage tool. When the build reaches a reviewable PR (or hits its circuit breaker / a
blocker), send EXACTLY ONE structured message:
  SendMessage(to="team-lead", summary="builder-{TICKET} done|blocked",
              message="<state: PR #N created, CI <green|red: which checks> | blocked at <step> because <reason>>")
REPORT CI HONESTLY: before you report "done", run `gh pr checks {PR}` and include the real check
state in your message. A PR with a failing check or unresolved Major/Critical review thread is
**not** "done/all-green" — say "PR #N created, CI red: <checks>" so the lead reviews the truth, not
an over-claim. Do not assert "tests pass / review passed" from your local run alone; CI is the
source of truth. Even if you stop early, send the message first. Then mark your task completed via TaskUpdate.
```

### Step 7: Monitor + roll-up (Lead observes)

⚠️ **The two rules the Lead most often gets wrong — read them first, follow them literally:**

1. **Idle ≠ done. Never nudge on idle alone.** A builder running a full build idles repeatedly
   between turns; a contentless `idle_notification` is NOT a completion signal and NOT a problem.
   Wait for the builder's actual `SendMessage` — it can take many minutes of silence.
2. **State-as-truth.** Never make "is this Story done" depend on a message arriving. When you
   need to know a builder's state (long idle, ambiguous report, before any roll-up claim), run
   this checklist instead of guessing:
   1. `orchestration.py story status {TICKET}` — which checkpoints exist (`pr_created`/`ci_passed`)?
   2. `git log` on the builder's branch — are commits landing?
   3. `gh pr checks {PR}` if a PR exists — what is CI *actually* saying?
   4. Only after 1–3: nudge the builder, **at most once**.

Builders report via the shared task-list and `SendMessage` (delivered automatically — do not
poll a terminal). Track per-builder state (dispatched → building → PR-ready / blocked).

When a builder is done/blocked (by message or by state), continue to Step 8 for that Story;
others keep running. Emit a running roll-up: `in-flight: {…} | PR-ready: {…} | blocked: {…}`.

### Step 7+ (`--refine-ahead`): refine the next story during build idle

When invoked with `--refine-ahead`, the idle window above becomes productive: the Lead refines the
**next** `refinable` story while builders run, so the build lane never starves. This is a **scheduler
overlay on Step 7**, not a new dispatch mode — it composes with Mode A.

> **P2 / P3 = the two rollout increments of this lane.** **P2** (phase 2, the default behaviour
> today): the Lead refines the next story **itself, interactively with the user**. **P3** (phase 3,
> below — OFF by default, gated on a rehearsal go/no-go): a Write-only **refiner-teammate** drafts the
> plan in parallel. Until a rehearsal GO enables P3, all refinement runs the P2 path.

The Lead runs this loop, re-running `story ready <epic>` each pass for fresh `{ready, refinable, held}`:

```
loop:
  # BUILD LANE (consumer) — fill to the ≤2 cap, disjoint-gated
  while in_flight_builds < 2 and ready non-empty:
      S = lowest-key ready story
      if S is DISJOINT from every in-flight build (see the disjoint guard) → rolling-confirm → dispatch builder(S)
      else → HOLD S (waiting on the conflicting build); stop filling (don't busy-pick a blocked story)
  # REFINE LANE (producer) — keep ~1 story ahead, never over-produce
  if refined-but-not-built < cap+1 and refinable non-empty:        # the buffer throttle
      R = lowest-key refinable story
      if R needs human design input              → Lead refines R interactively WITH the user   (P2)
                                                    (clarify, draft docs/plans/{R}-story.md with the
                                                     DoR sections, get the user's nod)
      elif P3 ENABLED (rehearsal GO) and a refiner slot is free → dispatch ONE refiner-teammate(R) (P3)
                                                    (Write-only; the Lead verifies + checkpoints on return)
      else                                       → Lead refines R itself                          (P2)
      # (P3 is OFF by default — so absent a passed rehearsal go/no-go, refinement always runs P2)
      → then run `story ready` again: if R now passes (left `refinable`) it enters the build lane
        next pass; if not, keep refining / retry once / surface what's blocking
  # DRAIN on events
  on builder-done:  review the PR (Step 8) + `gh pr checks`; recompute and refill the build lane
  on refiner-done:  the Lead runs `story ready` (verify R left `refinable` — the body scan, not any
                    checkpoint, is what moves it) → pass: `story checkpoint refined` (durable record)
                    + commit the plan to main; fail: retry once, else hand to the P2 lane
  # TERMINATION — the predicate that prevents spin/hang
  if no dispatchable-ready story AND refinable is empty AND in-flight (builders+refiner) is empty:
      terminate + report the held set with reasons   # never loop
  else: wait for the next event   (idle ≠ done — do not nudge on idle alone)
```

**The disjoint guard (a hint, not a guarantee).** Before dispatching a ready story while another
build is in flight, check file overlap: union each story plan's per-phase `**Files:**` lists and
set-intersect the to-dispatch story's union against each in-flight build's union; non-empty → **hold
until the conflicting build lands**. Be honest about its limits — cross-story file lists are coarse
(the plans were authored independently), a shared *seam* (the `select_responders`/`pending` case —
same function, not an obviously-shared filename) is invisible to a naive intersection, and the Lead
cannot see a builder's *uncommitted* edits. **When in doubt, serialize** (the Mode B rule): missing
file lists, any detected overlap, or any doubt → surface it in the rolling confirm ("WA-X and
in-flight WA-Y may both touch `select_responders.py` — dispatch or hold?") and default to hold.
(The base Step-6 dispatch does **not** run this guard — there the ≤2 ready Stories are assumed
independent by `depends_on`; the file-level check is added only here, because `--refine-ahead` lets a
*just-refined* story join a build that is already in flight, which `depends_on` never vetted.)

**Rolling confirm, not one-shot.** Step 3's confirm gate becomes continuous: each new build dispatch
gets a lightweight user confirm in the loop. The human stays the tiebreaker for the disjoint guard
and the cap.

**Termination correctness:** "all `refinable` conflict with in-flight builds" is correct
serialization (hold-until-clear), **not** deadlock — a held story becomes dispatchable on the next
builder-done + recompute. A `depends_on` **cycle** (`compute_ready_set` does not detect cycles)
drains to the termination predicate and is reported as `waiting on …` — name the cycle, don't wait
forever. A refine succeeds **iff** the story leaves `refinable` (i.e. `_body_is_refined` now passes) —
NOT merely "file written" and NOT "appears in `ready`" (it may be held by cap/disjoint).

### Step 7+ P3: the autonomous refiner-teammate lane (OFF by default)

P3 adds a Write-only **refiner-teammate** (≤1) that drafts the next plan in parallel while the Lead
talks to the user. It is **gated on a `--rehearsal` go/no-go** and disabled until that passes — absent
a GO, all refinement runs P2. Full mechanics, duty split, and the Refiner-Brief:
[`references/refine-ahead-p3.md`](references/refine-ahead-p3.md). Read it before dispatching a refiner.
Core invariants (also in Rules): refiner only Writes; the Lead alone verifies (`story ready`),
checkpoints, and commits; brief is a direct template, never a `/we:story` invocation.

### Step 8: Review each finished PR + record end

For each builder that reported a PR: the **Lead reviews** it (in the Companion review voice if
MCP-resolved, else the generic review lens) against the Story's ACs. This is the second human
gate — surface the review to the user; the Lead does **not** merge. The completion is already in
`orchestration.py` (the builder's `/we:build` wrote `pr_created`/`ci_passed`) — confirm it via
`story status {TICKET}` for the roll-up rather than writing it.

**Check CI status before declaring the review passed — a diff read is not a review (hard-won). Order: FIRST pull the CI rollup, THEN read the diff.**
A clean-looking diff can still fail CI: the new build target breaks, a review gate has
unresolved Major/Critical threads, an env-only check goes red. Always pull the live check rollup
— `gh pr checks {PR}` (or `gh pr view {PR} --json statusCheckRollup`) — and treat **any** red
check as "not reviewable-passed yet". A builder reporting "done, all green" is a *claim*, not
evidence; the rollup is the evidence. When CI is red, the review verdict is **changes-needed**,
and the next move is `/we:ci-review {PR}` (fix the checks + threads), not merge. Never tell the
user a PR is merge-ready while a single required check is red.

If a builder reported blocked, surface the blocker — do not silently retry.

### Step 9: Final roll-up + close the team

Emit the final roll-up (shipped-to-review / blocked / held-by-cap). Then:

```python
TeamDelete()
```

Always close the team, even on failure paths — a leaked team blocks the next run in this
session. If `TeamDelete` fails because a builder is still finishing, wait 30 s and retry twice,
then warn and continue.

**`TeamDelete` ≠ full teardown.** Mandatory sequence: (1) shutdown message to every member → (2) `TeamDelete()` → (3) `pkill` the team's agent procs → (4) `tmux kill-pane` leftover idle panes. Exact commands + retry policy: `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md` § Full teardown.

---

## Mode B — Lead-integrated phase dispatch (one coherent change, many phases)

The Step 1–9 workflow dispatches **one builder per Story, each running the full `/we:build`**. That
is right when the ready Stories are **independent, sprint-sized slices**. It is the **wrong shape for
a single coherent change split into phases** — a large refactor, a migration — where N full builds
would pay the entire QS cost (characterization + AC-gate + simplify + the parallel quality-gate
subagents + docs + PR + CI) **N times over**. Cutting such a change into N Stories just to dispatch
it multiplies overhead the work does not need; the human feels that overhead and is right to refuse it.

For that case, run the **lead-integrated phase mode**:

- The Lead holds the **one** Story/Epic **and its phase decomposition** (the Lead already cut it into
  phases — that *is* the overview it holds).
- Dispatch the phases as **lead-held work-chunks (tasks, not Stories)** via `TaskCreate` +
  `Agent(team_name=…, name=…)`. Teammates do **focused implementation only** — **not** the full
  `/we:build`, **not** a per-chunk PR. Their brief is scoped to exactly one chunk.
- Each teammate works its chunk in its own worktree, runs its **targeted** tests, and reports to the
  Lead via `SendMessage`.
- The Lead **reviews each diff and integrates it onto one integration branch** — holding the thread,
  reading reports (not full transcripts) to keep its own context clean.
- The heavy QS runs **once, at the end, by the Lead**: full suite + arch gates + `/we:review` +
  `/we:docs` + bypass register, then **one PR** for the whole change.
- **Characterization-as-contract.** The first chunk writes a characterization net that pins current
  behaviour (green on unmodified code); every later chunk must keep those assertions **unchanged** —
  editing one is a deliberate, reviewed behaviour change, never a silent diff. The integration QS
  asserts they still pass. This is the no-regression guarantee that lets the change land as one cut.
- Same guards as Mode A: the ≤2-concurrent cap, the confirm-to-dispatch gate, Lead-reviews, and
  **human merges**. Risk-driven order: a serial foundation chunk that **freezes the interface** first,
  then the disjoint chunks in parallel, then a final integration chunk the Lead owns.

**Choosing the mode (Step 3).** Independent ready Stories → the per-Story full-build workflow (Mode A).
One ready Story that is really a phased change the Lead has decomposed → this lead-integrated mode
(Mode B). When in doubt, ask the human which shape the work is.

### Mode B field lessons (mandatory read before dispatching chunks)

Read [`references/mode-b-lessons.md`](references/mode-b-lessons.md) **before the first chunk dispatch**
— it carries the hard-won detail behind the Mode B rules below: the parallelism discriminating check
(shared scaffolding = serial foundation chunk; re-check at every wave boundary), worktree hygiene
(teammate worktrees off the integration branch, Lead never flips the main worktree), chunk-brief
discipline (mid-tier model default, surface forks before pinning, pins capture existing behaviour
only), and chunk review (green is the start of review, validate the integrated tree at full scope,
Lead owns cross-cutting glue, confirm the worktree root before trusting a green).

---

## Rehearsal mode (`--rehearsal`)

Run the complete pipeline against a committed fixture instead of a real epic — the lab for shaking
out skill bugs and for the P3 go/no-go. Full procedure: [`references/rehearsal.md`](references/rehearsal.md).

---

## Standalone fallback

No weside account / no MCP → the Lead reviews with the generic role lens, builders run normally
(builds never needed identity). Everything else is identical. The Agent-Teams env-flag is
required regardless of weside connection.

## Rules

- **Boot from state on every invocation** — reconstruct where the Epic stands from living files
  before anything else; never assume cached knowledge.
- **Dispatch only on an explicit confirm** — the ready set is shown first; the human gates it.
- **Hard cap ≤2 concurrent builders** — refuse and log any attempt to exceed it (runaway guard).
- **The Lead is a persistent partner, not a throwaway dispatcher** — it holds the overview so the
  human is not overwhelmed (see *The stance*). In Companion mode it *is* the Companion.
- **Pick the dispatch shape (Mode A vs Mode B)** — independent Stories → builders run the full
  unmodified `/we:build` (Mode A); one phased coherent change → lead-integrated phase dispatch where
  teammates do focused chunks and the Lead integrates + runs QS once → one PR (Mode B).
- **Mode A: builders run the full unmodified `/we:build`** — never reimplement or degrade the
  build/QA; a teammate spawns the build's own subagents (validated: a builder ran `/we:build` through
  Step 5's parallel quality-gate subagents and wrote durable checkpoints). In Mode B, teammates run a
  scoped chunk (not the full build) and the Lead owns the single end-of-change QS.
- **Mode B: run the parallelism discriminating check before fanning out** — chunks parallelize only if
  each touches solely its own files; shared scaffolding that several phases must fill is a serial
  foundation chunk, not parallel work. A chunk that makes shared scaffolding real runs serial-first.
- **Mode B: worktree-per-teammate; the Lead never flips the main worktree** — teammates branch their
  own worktree off the integration branch; the Lead integrates in a dedicated lead worktree; the main
  worktree stays on the default branch for the whole run.
- **Mode B: green is the start of review, not the end** — evaluate a builder's surfaced fork-decision
  against the acceptance criterion, not the test status; never accept an over-claimed characterization
  net, and approve a behaviour-locus move only explicitly, in the commit.
- **Mode B: default builders to the mid-tier model, escalate to the top tier only for a named-hard chunk**
  — the Lead must be able to say *why* a chunk needs the top tier (delicate ordering, teardown, a freeze);
  otherwise the faster/cheaper model is the right fit. Make escalation an explicit per-chunk choice.
- **Mode B: validate the integrated tree at full scope after each merge, and own the cross-cutting glue**
  — a chunk's narrow green can hide a latent error in a sibling file; the Lead re-runs broad checks on the
  merged branch and fixes out-of-scope breakage itself as a separate, labelled integration commit. Confirm
  the worktree root before trusting any validation — a green from the wrong directory proves nothing.
- **Mode B: brief builders to surface forks before pinning, and to pin existing behaviour only** — a real
  design fork goes to the Lead *before* the characterization is written; pins capture what already exists
  (green on unmodified code), never a property the migration newly adds.
- **`--refine-ahead` is a Step-7 overlay, not a third mode** — it composes with Mode A; the build
  lane stays ≤2 and disjoint-gated, the refine lane keeps ~1 story ahead (`refined-not-built < cap+1`,
  never over-produce). Default (flag off) = passive monitoring, unchanged.
- **`--refine-ahead`: serialize on doubt (the disjoint guard is a hint)** — only dispatch a ready
  story alongside an in-flight build when their plan `**Files:**` are disjoint; missing lists, any
  overlap, or a shared *seam* you can't see in the file lists → surface it in the rolling confirm and
  default to hold. A refine succeeds only when the story leaves `refinable` (`_body_is_refined`
  passes), never on "file written" alone.
- **`--refine-ahead`: never spin or hang** — terminate iff dispatchable-ready, refinable(+buffer), and
  in-flight are ALL empty; report the held set (incl. any `depends_on` cycle) with reasons rather than
  looping.
- **`--refine-ahead` P3 (refiner-teammate): ≤1 refiner, and the refiner only Writes** — the Lead is the
  single writer/verifier (runs `story ready` + `story checkpoint refined` + commit); the refiner never
  runs git/orchestration. Use a *direct template* brief, never a `/we:story` invocation (it would stall
  at ExitPlanMode). Enable the P3 lane only after a `--rehearsal` go/no-go proves it; P2 is the fallback.
- **Spawn builders with `Agent(team_name=…, name=…)`, all in one message** — never `Skill` for
  teammates. Builders live in their own watchable sessions.
- **Never inject Companion identity into builders** — user-scoped `select_companion` race; only
  the Lead carries a voice.
- **Lead reviews, never merges** — Deliver (merge, close ticket, move to Done) is the human's job.
- **Always `TeamDelete` on teardown** — even on failure paths.
- **Fail loud on the env-flag, degrade gracefully on identity** — same contract as `/we:council`.

## References

- `references/mode-b-lessons.md` — hard-won Mode B field lessons (mandatory read before chunk dispatch)
- `references/refine-ahead-p3.md` — the autonomous refiner lane (off by default) + Refiner-Brief
- `references/rehearsal.md` — `--rehearsal` procedure + P3 go/no-go
- `references/fixture-story.md` + `references/fixture-refinable-story.md` — rehearsal fixtures
- `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md` — env-flag prerequisite + full teardown
- `we/skills/council/SKILL.md` — the Agent-Teams machinery this skill mirrors
- `we/skills/build/SKILL.md` — the pipeline each builder runs unmodified
- `scripts/orchestration.py` — `story status|list|checkpoint|ready` (tracking + ready-set)
- `scripts/test_ready_set.py` — unit tests for the `compute_ready_set` pure helper
