---
name: orchestrate
description: >
  Epic-driven build orchestration. The Lead boots from state like a colleague —
  reconstructs where an Epic stands from its plans, frontmatter, ticketing mirror,
  and build-state — computes the ready set of buildable Stories, and (on confirm)
  dispatches one builder-teammate per Story running the full /we:build, tracking
  each in the shared task-list + orchestration DB. The Build-altitude sibling of
  /we:council. Use when the user says "/we:orchestrate", "orchestrate the epic",
  "dispatch the ready stories", "run the builds", "kick off the ready builds". For a
  read-only status snapshot of an Epic, use /we:epic instead — orchestrate is the
  dispatch-altitude sibling that actually spawns builders.
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

Agent Teams must be enabled — same flag as `/we:council`. In `~/.claude/settings.json`:

```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

A session restart is needed after toggling. If the flag is missing when dispatch runs, the
skill aborts in Step 4 with a remediation hint — there is no non-team fallback.

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
/we:orchestrate <epic>              # boot + status + ready-set; dispatch only on confirm
/we:orchestrate <epic> --rehearsal  # run the pipeline against a fixture, no real PR/ticket
/we:orchestrate                     # boot from the most recently active epic, then status
```

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
explicit confirm.** If `--rehearsal`, skip to the Rehearsal section instead.

### Step 4: Preflight

1. **Env-flag check** — confirm `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. If missing, abort:

   ```
   /we:orchestrate needs Agent Teams enabled.

   Add this to ~/.claude/settings.json:
     { "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
   Then restart your session. Or run /we:setup — it sets the flag for you.
   ```

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

Builders report via the shared task-list and `SendMessage` (delivered automatically — do not
poll a terminal). Track per-builder state (dispatched → building → PR-ready / blocked).

**Idle ≠ done.** A builder running a full build idles repeatedly between turns; a contentless
`idle_notification` is NOT a completion signal and NOT a problem. Wait for the builder's actual
`SendMessage` — it can take minutes. Do not nudge on idle alone.

**State-as-truth (the robustness rule).** Never make "is this Story done" depend on a message
arriving. The source of truth is `orchestration.py story status {TICKET}` (checkpoints
`pr_created`/`ci_passed`) + the builder's branch. If a builder has been idle a long time with no
message, read its `story status` + branch directly to determine state, and nudge at most once.

When a builder is done/blocked (by message or by state), continue to Step 8 for that Story;
others keep running. Emit a running roll-up: `in-flight: {…} | PR-ready: {…} | blocked: {…}`.

### Step 8: Review each finished PR + record end

For each builder that reported a PR: the **Lead reviews** it (in the Companion review voice if
MCP-resolved, else the generic review lens) against the Story's ACs. This is the second human
gate — surface the review to the user; the Lead does **not** merge. The completion is already in
`orchestration.py` (the builder's `/we:build` wrote `pr_created`/`ci_passed`) — confirm it via
`story status {TICKET}` for the roll-up rather than writing it.

**Check CI status before declaring the review passed — a diff read is not a review (hard-won).**
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

### Sequencing the chunks (hard-won on the first real run)

- **The parallelism is usually less than it looks — run the discriminating check before fanning out.**
  Ask of each "disjoint" chunk: *can it land touching only its own files, with zero edits to any
  shared file the other chunks also need?* The trap is a shared file every phase has to make real —
  not just the named interface you froze, but any common helper the phases fill in. If two chunks
  would both edit it, they are **not** disjoint; that shared work is **another serial foundation
  chunk**, done once before the per-unit chunks parallelize. Found the hard way: two units looked
  independent but both had to fill the same shared scaffolding — parallel dispatch would have collided
  at integration. Rule of thumb: a chunk that *makes shared scaffolding real* (freezes a contract every
  later chunk consumes) is **foundation-completion → serial-first**. You cannot race a chunk against
  the thing it depends on becoming real. The real parallelism appears late — in the per-unit wiring,
  once the shared scaffolding is frozen.
  - **There is often more than one shared layer — re-run the check at *every* wave boundary, not once.**
    On the real run two distinct shared layers surfaced (a shared dispatch seam *and* a shared set of
    gate-stage files); each needed its own serial freeze-chunk before the per-unit chunks could
    parallelize. Don't assume one foundation chunk clears the way. Before each parallel wave, re-ask the
    discriminating question against what's *still* unfrozen; collapse to serial whenever the answer is no.
- **Worktree hygiene is non-negotiable.** Each teammate works in its **own** worktree branched off the
  integration branch (so it carries the prior integrated chunks); the Lead integrates in a **dedicated
  lead worktree**; the Lead **never** flips the *main* worktree's branch. Flipping the shared main
  worktree between branches mid-orchestration lands commits on the wrong branch and lets a stray rebase
  rewrite a teammate's pushed work — a real, repeated failure mode. The main worktree stays on the
  default branch, untouched, for the whole run.

### Writing the chunk brief (Mode B)

- **Default builders to the mid-tier model; reserve the top tier for a deliberately-hard chunk.** Routine
  implementation chunks run fine on the faster/cheaper model (e.g. Sonnet); spend the top tier (e.g. Opus)
  only where the Lead can name *why* it's hard — delicate ordering, a boss-fight teardown, a contract
  freeze every later chunk depends on. Reflexively spawning the top tier for every chunk is the wrong
  cost/fit. Make the escalation an explicit, justified per-chunk choice, not the default.
- **Invite the builder to surface a fork *before* it pins behaviour.** The brief should say: if you hit a
  real design fork (which transport, which failure semantics, which seam), send it to the Lead *before*
  writing the characterization — so the Lead's call shapes the pins, instead of forcing a rework after.
  The best builders do this unprompted; ask for it explicitly so the rest do too.
- **A characterization pin is for behaviour that *already exists*, not a gain the migration adds.** Tell
  builders to pin the current behaviour (green on the unmodified code), and to flag — not pin — any
  property the refactor newly *introduces* (it would be red-on-old-code, so it isn't characterization).
  Confusing "preserve what's there" with "the new thing we're adding" produces a pin that can't go green
  first; a sharp builder will push back on a brief that asks for it, and they're right.

### Reviewing a chunk (the Lead's core act)

- **"All green" is the start of review, not the end.** When a builder honestly surfaces a decision it
  made at a fork (the good ones do — invite it in the brief), evaluate it against the **acceptance
  criterion**, not the test status. Green tests pin what they cover; the edge that breaks the AC is
  usually the one no pin covers (e.g. a happy-path net that silently changes an error-path contract).
  An over-claimed safety net — a characterization docstring claiming more than it pins — is worse than
  an honest gap, because it reads as covered when it isn't.
- **Moving a behaviour's locus is an allowed, explicit characterization change.** When a refactor moves
  *where* a behaviour is produced — same observable outcome, different internal actor — the Lead may
  explicitly approve rewriting the pin to the new locus, noted in the commit. That is reviewed and
  intentional, categorically different from silently weakening an assertion to make a build pass: the
  test still proves the observable behaviour; only the thing it watches moved.
- **Validate the *integrated* state broadly — a chunk's own green is scoped to its files.** Each teammate
  runs narrow checks (its files, its tests). A foundation chunk that changed a shared contract can leave
  a latent error in a *sibling* file no chunk's narrow gate covers — it only surfaces when the Lead runs
  a broad check on the merged tree. So the Lead's integration step re-runs the type-checker/tests at full
  scope after each merge, not just the chunk's slice. (Real run: a contract change in one foundation chunk
  left a type error in an unrelated adapter; every chunk was green, the integrated branch was not.)
- **The Lead owns cross-cutting integration glue.** When that broad check finds a latent error in a file
  outside every chunk's scope, the Lead fixes it *itself* as a small, clearly-labelled integration commit
  (delete the dead code, the one-line conformance fix) — it does not expand a teammate's scope to reach
  into a file it was told to leave alone. Keep the glue commits separate and named so the history stays
  honest about what was chunk work and what was integration.
- **Watch your own working directory when integrating across worktrees.** The Lead juggles several
  worktrees; a mid-command `cd` into the wrong one makes a validation run silently test the *wrong* tree
  (it passes, but it proved nothing about the integration branch). Re-confirm the worktree root before
  trusting a green. A green from the wrong directory is worse than a red.

---

## Rehearsal mode (`--rehearsal`)

Run the complete pipeline **without a real epic/story/code** — to shake out where the skills
stumble and optimise them. Repeatable via the built-in `/loop` skill
(`/loop /we:orchestrate FIXTURE --rehearsal`).

1. Set up a throwaway repo (or worktree) and copy the committed fixture template
   `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/references/fixture-story.md` into it as
   `docs/plans/FIXTURE-story.md`. Its AC is trivial but **real** (a pure `rehearsal_noop() -> 42`
   with a test) so the real review/test/PR steps have a genuine diff to chew on — a fully mocked
   no-op would short-circuit the skills and prove nothing.
2. Dispatch exactly one builder for the fixture, but instruct it: target a **throwaway worktree**,
   **plan-only ticketing** (no Jira transitions), and **no real PR** — create a draft on a scratch
   branch and delete it on teardown, or stop before push.
3. Run the **real** Step 1–8 build logic so genuine skill bugs surface.
4. Append the friction points (which step stumbled, the exact error) to a rehearsal log:
   `docs/retros/YYYY-MM-DD-orchestrate-rehearsal.md` (repo-relative, under the story repo root).
5. `TeamDelete`, delete the scratch worktree/branch. Loop to repeat.

This is the lab for the broader skill clean-up: each iteration → `plugin-dev:skill-reviewer` /
`plugin-validator` against the skill that stumbled → targeted fix → re-loop.

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
- **Spawn builders with `Agent(team_name=…, name=…)`, all in one message** — never `Skill` for
  teammates. Builders live in their own watchable sessions.
- **Never inject Companion identity into builders** — user-scoped `select_companion` race; only
  the Lead carries a voice.
- **Lead reviews, never merges** — Deliver (merge, close ticket, move to Done) is the human's job.
- **Always `TeamDelete` on teardown** — even on failure paths.
- **Fail loud on the env-flag, degrade gracefully on identity** — same contract as `/we:council`.

## References

- `we/skills/council/SKILL.md` — the Agent-Teams machinery this skill mirrors
- `we/skills/build/SKILL.md` — the pipeline each builder runs unmodified
- `we/skills/epic/SKILL.md` — the boot-from-state / mirror pattern for "where we stand"
- `we/skills/map/SKILL.md` — plan-tree rendering across `docs/plans/`
- `we/skills/handoff/SKILL.md` — the durable cross-session bridge the Lead reads at boot
- `scripts/orchestration.py` — `story status|list|checkpoint|ready` (tracking + ready-set)
- `scripts/test_ready_set.py` — unit tests for the `compute_ready_set` pure helper
- `skills/orchestrate/references/fixture-story.md` — the rehearsal fixture template
