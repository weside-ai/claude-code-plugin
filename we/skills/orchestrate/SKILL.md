---
name: orchestrate
description: >
  Multi-chunk orchestration — the Lead dispatches dev-only workers (cheap
  Claude / Codex / foreign engine) per Story or per phase, integrates their
  branches onto one integration branch, and runs CI once on a single PR.
  Use when the user says "/we:orchestrate", "orchestrate the epic",
  "orchestrate this story", "dispatch the ready stories", "run the phases".
---

# /we:orchestrate

**Purpose:** Stop being the manual courier between a planning session and per-Story build
sessions. The Lead — the session running `/we:orchestrate` — is a persistent colleague that
boots knowing where the Epic stands, holds context, computes which Stories are ready, dispatches
them as dev-only workers, integrates their branches, and reviews the combined diff. CI runs
**once** on the integration PR — not once per worker. It never merges — Deliver stays human.

**Cost model:** workers run on cheap-tier Claude (Sonnet/Haiku), Codex, or a foreign engine.
The Lead (the expensive session model) plans, integrates, and reviews. N workers = N dev costs
+ one integration CI, not N full pipelines. A story too small to be worth a worker runs
`--solo` — same pipeline, nothing dispatched.

> **One pipeline, three dispatch shapes.** Every run ends the same way: implement → simplify →
> AC/DoD gate → **verification** → quality gates → docs → PR → one CI pass. That half is owned by
> [`references/integration-pipeline.md`](../../references/integration-pipeline.md) and is
> identical whether the code came from one worker, five, or the Lead's own hands. What differs is
> only *who implements*: workers per Story (Mode A), workers per phase (Mode B), or nobody
> (`--solo`).

This is the **Build-altitude sibling of `/we:council`/`/we:meet`**: the same Agent-Teams
machinery (spawn into the session's implicit team via `Agent(name=…)` → `SendMessage` →
shutdown-message teardown), but the teammates are **dev workers** running `/we:develop`, not
deliberators.

**The stance (not just the mechanics).** The Lead is a *persistent partner*, not a throwaway
dispatcher. It boots knowing where the work stands, **holds the overview so the human is not
overwhelmed**, plans and assigns the work, and integrates and evaluates what comes back. The human
is good at saying *where we want to go*; the Lead carries it *on the way* — that continuity, someone
holding the whole across the dispatch loop, is the point. When a Companion is materialized, the Lead
is that Companion (warmth + presence, not manager-speak), not a generic dispatcher.

## Prerequisites

```
Read("${CLAUDE_PLUGIN_ROOT}/references/verification.md")
Read("${CLAUDE_PLUGIN_ROOT}/references/long-running.md")
```

Agent Teams must be enabled — same flag, abort text, and teardown contract as `/we:council`: see `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md`. No non-team fallback.

**Permission mode must allow teammate Bash — check before dispatch, not after.** A worker's job is
almost entirely Bash (git, gh, the orchestration CLI). Under the default/auto mode the classifier
denies *every* teammate Bash call, because a teammate-message-triggered invocation carries no direct
user intent: the worker is dispatched, reaches its first command, and is dead on arrival with "Bash
denied" and nothing written. So the session must be on **`acceptEdits`** (or bypass), or carry a
Bash allowlist for the multi-agent path. Surface this at Step 3's confirm gate; if you cannot tell
the mode, ask. `--solo` needs none of this — it dispatches nothing, so it is the honest answer
when a single small story would otherwise pay the whole team's setup cost.

## Invocation

```
/we:orchestrate <epic>                 # epic target: boot + status + ready-set; dispatch on confirm (Mode A)
/we:orchestrate <story-key>            # single-Story target: run THIS story's phases as work-chunks (Mode B)
/we:orchestrate <story-key> --solo     # single Story, no workers: implement here, then integrate
/we:orchestrate <epic> --refine-ahead  # build the ready stories AND refine the next during build idle
/we:orchestrate <epic> --rehearsal     # run the pipeline against a fixture, no real PR/ticket
/we:orchestrate                        # boot from the most recently active epic, then status
```

`--refine-ahead` turns the Step-7 monitoring window into a **two-lane pipeline**: while builders run
(minutes of Lead idle), the Lead refines the **next** `refinable` story so it is build-ready by the
time a builder frees — overlapping build-time and refine-time. It composes with the per-Story build
shape (Mode A); it is **not** a third dispatch mode. Default (flag off) = today's passive monitoring.
(`--refine-ahead` and `--rehearsal` apply to **epic targets only** — a single-Story target has no
ready-set to refine ahead of.)

**Refine two or three ahead, not the whole backlog.** The temptation, once the refine lane
works, is to bank a deep queue of build-ready plans so dispatch never waits. Don't: a plan
refined five waves early is written against a `main` that will not exist when its builder picks
it up. Observed on a 14-story epic — a story's plan promised a workspace-scope hook the design
had deleted weeks earlier, and the waves themselves ran out of their planned order, so several
plans had to be rewritten before they could be built. Two ahead is the depth at which a plan is
still true on arrival; beyond that "plans are living" quietly means writing each one twice.

### Target resolution (Step 0 — do this before booting)

The argument is either an **Epic** or a **single Story**. Resolve it once, it picks the whole shape:

+ **Single-Story target** when the argument matches a Story plan `docs/plans/{KEY}-story.md` (or its
  ticket key resolves to one Story) AND there is no Epic plan / no other story shares it as an `epic:`.
  → **Skip Step 2 entirely (no ready-set)** and run **Mode B** over that one plan's `### Phase` blocks.
  This is the low-overhead path `/we:story` recommends for a single multi-phase (or context-heavy)
  change — no synthetic epic, no ready-set. Honour the plan's `parallel_groups` for the parallel waves.
+ **`--solo`** forces the single-Story shape and skips dispatch entirely — see the `--solo`
  section below. It is the only flag that changes *who implements*.
+ **Epic target** otherwise (an Epic plan exists, or ≥1 story shares the slug/key as `epic:`).
  → the full Step 1–9 workflow (boot, ready-set, per-Story builders = Mode A; one phased Story in the
  set may itself run Mode B per Step 3's mode choice).

`<epic>` is an Epic **slug** (e.g. `circles`) or a ticketing Epic key (e.g. `PROJ-1205`) — either
works. Stories may reference their epic by slug or by key; `story ready` resolves both via the
Epic plan's `epic:`/`ticket:` frontmatter (`_resolve_epic_identifiers`). A `<story-key>` is a single
Story ticket/plan key (e.g. `PROJ-1330`).

---

## Workflow

### Step 1: Boot from state (always — this is the colleague's first act)

> **Single-Story target shortcut.** If Step 0 resolved a **single Story** (not an epic): read just
> that one plan `docs/plans/{KEY}-story.md` completely + its build state
> (`orchestration.py story status {KEY}`) + any recent handoff, render a one-line stand
> (`{key} {title} — plan:{refined|incomplete} build:{phase|—} pr:{#|—}`), then **jump straight to
> the confirm gate (Step 3) and Mode B** — the ready-set (Step 2) does not apply to a single story's
> phases. The Mode-B section below is the execution path. The rest of Step 1 is the epic-target boot.

**Programme-scale work** (an epic with several waves, spanning sessions and compacts) also reads
`${CLAUDE_PLUGIN_ROOT}/references/programme-discipline.md` at boot — the state file, living plans,
self-verification and the `/loop` shape. If the epic has a `docs/plans/<epic>-state.md`, that file
is the FIRST thing read and the LAST thing written in every run; if it does not exist and the epic
spans more than one wave, creating it is the run's first act.

Before anything else (epic target), reconstruct "where we stand". Read the **living** files so the
picture is always current — never rely on cached knowledge:

1. **Epic frame** — read the Epic plan `docs/plans/*<epic>*-epic.md` if one exists; its
   `## Success Criteria` / scope are the lens for "what done means". If there is no epic file
   (and no Saga mirror row), **degrade gracefully**: synthesise the frame from the child
   Stories that share this `epic:` slug — do not abort. An epic slug backed only by Story plans
   is valid (a rehearsal or a freshly-cut epic).
2. **Child Stories** — glob `docs/plans/*-story.md`, keep those whose frontmatter `epic:`
   matches `<epic>`. For each, read frontmatter (`story`, `status`) and scan the body for DoR
   completeness (the 3-item scan in `${CLAUDE_PLUGIN_ROOT}/references/dor-scan.md`).
3. **Ticketing mirror** — if a ticketing tool is available (weside MCP `JIRA_*` → Atlassian MCP
   → `gh`), fetch each Story's ticket status **and its comments** — comments carry corrections
   and scope cuts the plan file may predate; newest statement wins on conflict and you name the
   conflict (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`). No ticketing tool → use plan
   frontmatter `status` only (same fallback as `/we:epic`).
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

**The function has no notion of "already dispatched", so read its output against your own
in-flight list.** `built` is derived from a ticket status or a `pr_created`/`ci_passed`
checkpoint — none of which exists while a worker is still writing. A dispatched story therefore
keeps appearing in `ready`, and can be pushed to `held: cap reached` by a story you refined
*after* dispatching it. Neither is wrong; both are the pure function saying "nothing durable has
happened yet".

Two places this bites, both avoidable:

+ **Under `--refine-ahead`,** a freshly refined story entering `ready` displaces a dispatched one
  in the cap accounting. Keep your own `in_flight` set and fill the build lane from
  `ready − in_flight`, not from `ready`.
+ **On a resumed run** (after a compact, a new session, or a crash), `ready` is the *only* thing
  you have — and it will happily offer a story whose worker is still running or whose branch is
  already pushed. Before dispatching anything on a resume, check for its branch and worktree
  (`git worktree list`, `git branch --list 'feat/{KEY}-*'`) and treat either as in-flight.

This is the same class as the checkpoint regression fixed in Step 6 — a durable record missing,
so the derived state lags reality. Here the missing record is deliberate (a dispatch is not an
outcome), which is exactly why the Lead has to hold it.

### Step 3: Confirm gate (human-in-the-loop)

Present the ready set and ask the user to confirm dispatch. This is the first of three human
gates (the others: Lead reviews each PR in Step 8; human merges). **Never dispatch without an
explicit confirm.** If `--rehearsal`, skip to the Rehearsal section instead. (Under `--refine-ahead`
this one-shot gate becomes a **rolling** confirm — one per new dispatch — see Step 7+.)

### Step 4: Preflight

1. **Env-flag check** — confirm `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`; if missing, abort with the remediation hint from `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md`.

2. **Concurrency cap (default ≤2)** — the default is 2 concurrent workers. If the ready set is
   larger, dispatch the first 2 (lowest Story key first) and log the rest as held. **The Lead may
   raise the cap** when the work is demonstrably disjoint and the context can hold it — state
   the reason explicitly before doing so. A raised cap with uncertain disjointness is a
   judgment call; when in doubt, keep the default.

   **Pair a frontend story with backend slices — not two frontend stories.** Backend work is
   the cheap concurrency: separate modules under one service tree rarely touch the same file,
   while two frontend stories in one wave collide on shared surfaces almost by default. A
   14-story UI epic paid for this twice — two workers editing one inline i18n resource produced
   three merge conflicts and a duplicated key, and another pair left a directory duplicated
   under two spellings of the same word. Neither worker could see it; each was right about its
   own slice, and it surfaced only at integration.

   So a cap of 3 is usually safe as **one FE + two BE**, and usually wrong as three FE. Judge
   by the file lists in the plans' phases, not by the stories' topics: "different areas" is not
   the test, *different files* is — a mature `components/` directory can hold fifty of them.

   **When one file is genuinely shared, assign sections instead of serializing.** The advice
   above used to end here, and read as "then don't run that wave" — which is the wrong price
   when the collision is *one* file. A repo usually has a handful of single-file shared
   resources every frontend story must touch: an inline i18n bundle, a barrel export, a theme
   token file, a route manifest. Serializing a whole wave around one of them is expensive; the
   file is almost always a set of long, contiguous, far-apart blocks, and git merges those
   cleanly as long as two workers do not append to the *same* block.

   So, before dispatch:

   + **Name the shared file and give each worker disjoint top-level sections**, in the brief,
     in capitals, with the other worker's sections listed as forbidden. Assign by what the
     story actually touches — read the components' existing calls, do not guess from the story
     title.
   + **Declare the catch-all section read-only for everyone.** There is always one (`common`,
     `shared`, `misc`) and it is exactly where two workers otherwise both append. A worker
     needing a new shared-looking key puts it in its own section.
   + **Verify at merge, not by trust:** locate each hunk's line number in the file's section
     map and confirm it falls inside that worker's range. This costs one `git diff | grep '^@@'`
     and catches the failure the file-list disjoint guard is blind to by construction.

   Measured on a 14-story UI epic: the pairing rule alone had already cost three merge
   conflicts and a duplicated key across two waves. With sections assigned, a two-frontend-worker
   wave over a 7,494-line i18n file merged with every hunk inside its own namespace.

3. **Lead voice (MCP, optional)** — if `mcp__plugin_we_weside-mcp__get_council` exists, call it
   once for the Lead's review role (`product_owner` or `architect`, per `.weside/config.json`)
   and adopt that Companion's `identity_prompt` for the Lead's review voice in Step 8. Builders
   get **no** identity (the weside backend is user-scoped — parallel `select_companion` races;
   see `/we:council` "Memory in v1"). No MCP → generic review lens. Degrade gracefully.

4. **Create the integration branch in a dedicated worktree** — do this NOW, before any worker is
   dispatched. Workers branch off the pushed ref; the Lead merges their branches back here; the
   final PR runs against it. Creating it here ensures every worker has the same base.

   **The Lead never flips the *main* worktree's branch** — it stays on the default branch, untouched,
   for the whole run. Flipping it lands commits on the wrong branch and lets a stray rebase rewrite a
   worker's pushed branch; that is a real, repeated failure mode. Instead the Lead integrates from a
   **dedicated integration worktree** as a sibling of the repo
   (`$(git rev-parse --show-toplevel)-integration`), and every integration command below runs inside
   it via `git -C`. It is also the one place in the run that can afford a dependency install (B1c).

   On a resumed run, **never reset an existing branch or worktree**: reuse the worktree if it is
   there, add one onto the existing branch if only the branch is, and create both plus an upstream
   push only on a genuinely fresh run.

   The integration worktree lives until Step 9 — B3's ci-review fixes are committed in it.

### Step 5: Team is implicit — nothing to open

The current harness gives every session one implicit team; there is no `TeamCreate` call and no
`team_name` to generate. The Lead is simply the session that ran `/we:orchestrate`. Builders
become addressable teammates purely by being spawned with a `name` in Step 6 — proceed there
directly.

### Step 6: Dispatch builders (all spawns in one message) + record start

For each ready Story (≤2), create a task and spawn a builder-teammate. **All `Agent` spawns go
into a single assistant message** so they initialize concurrently.

```python
TaskCreate(subject=f"Build {TICKET}", description=f"Run /we:develop for {TICKET} to a pushed branch.")
Agent(
    name=f"worker-{TICKET}",
    subagent_type="general-purpose",
    model="sonnet",
    description=f"Build {TICKET}",
    prompt=<Builder-Brief — see below>,
)
```

The shared task-list (the `TaskCreate` above) carries the **live** dispatched/in-flight state.
The **durable** record is the Lead's to write: workers run `/we:develop`, which writes no
`story_workflow` rows at all, so `pr_created` and `ci_passed` land in Step 8 (B2/B4) and nowhere
else.

Two halves of the same regression sit behind that sentence, and both were expensive. When workers
moved from running the whole pipeline themselves to running dev-only `/we:develop`, nobody re-read
the paragraphs whose premise was "the worker does X": tickets stopped moving out of "In Progress",
and — unnoticed for longer — checkpoints
stopped being written, so stories that had shipped and merged still read as **unbuilt** and the
ready-set kept re-proposing them. **When a dispatch mode changes, re-read every paragraph whose
premise is what the worker does — not only the ones that name it.**

**Transition each dispatched Story → "In Progress" now (Lead owns this — workers do NOT).** If the
Lead doesn't move the ticket, nothing does. Detect the tool per
`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`, **verify** the move, retry once, soft-fail loud
only when the workflow rejects it. GitHub Issues / no ticketing tool → skip silently.

**Worker-Brief** (self-contained — the worker runs dev-only `/we:develop`):

```
You are worker-{TICKET}, a teammate spawned into this session's implicit team. The lead is "team-lead".

REPO: your working repo is {repo_root}. START EVERY bash command with `cd {repo_root}` and
confirm `git rev-parse --show-toplevel` is {repo_root} before any git operation.

BASE BRANCH: branch your worktree off `{integration_branch}` (e.g. `feat/{epic}-integration`),
NOT off main. /we:develop handles worktree creation — pass the base:
  Skill(skill="develop")  with the ticket {TICKET}  (the skill reads the integration base
  from its --base flag if given, or you can pass it in the context of this brief)

ISOLATION: /we:develop creates its own worktree — do NOT call EnterWorktree before invoking
the skill; the worktree is managed internally.

Your job: run the DEV-ONLY pipeline for {TICKET} via the skill.

DEV-ONLY means: implement all phases → **fast/unit local gates only** → AC-check your
diff → commit → push YOUR branch (e.g. `feat/{TICKET}-work`) → STOP.

TESTS: {test_discipline_instruction — the Lead reads `test_discipline` from
.weside/config.json and spells the level out here, e.g. "tests-after: write tests in the
same change, after the code". Always append: no implementation-coupled tests, no
tautological assertions, mock at system boundaries only.}

FAST GATES: run unit tests and fast smoke tests ONLY. Skip integration tests that need a
running database, queue, or network service — those belong to the integration CI the Lead
runs at the end. If unsure: if the test needs `docker-compose up` or an env variable like
`DATABASE_URL`, it is an integration test — skip it with a note in your report.
EXCEPTION — critical-path chunks: when this brief marks the chunk CRITICAL (money, auth,
tenant isolation) and names a local integration suite + database, RUN that suite before
reporting done — a critical chunk is never "fast gates only". (Field lesson: a money
migration shipped green through unit-only gates and would have broken production; only the
real-database suite catches the ON-CONFLICT/partial-index bug class.) The Lead decides
which chunks are critical and writes the suite + database into the brief.

ABSOLUTE NO-OPS (any of these voids the single-CI contract):
- DO NOT `gh pr create` — this triggers GitHub CI per worker, defeating the whole pattern; the
  Lead opens the one integration PR after every worker lands (Step 8)
- DO NOT run CI, do NOT wait for GitHub Actions (your `git push` may trigger `on: push`
  rules — IGNORE them; they are not your responsibility)
- DO NOT transition the ticket — the Lead owns ticket state and transitions it (Step 6 at
  dispatch, Step 8 B4 after integration)
- DO NOT run the integration pipeline — no PR, no CI, no doc pass, no ticket transitions
- DO NOT run frontend gates (`yarn`/`npm install`, `jest`, `tsc`) in a fresh worktree — it has no
  `node_modules` (~1GB) and building them is wasted setup. Implement the frontend changes, run
  ONLY touched-stack unit tests that need no install, and REPORT the skipped frontend validation;
  the Lead runs those install-gated gates locally at integration (Step 8 B1c), **before** the PR —
  CI is the second confirmation, not the first.
- After a change to a Pydantic schema referenced by a route, regenerate AND commit BOTH OpenAPI
  specs (`generate-openapi.py` → `openapi.json` + client spec), not just `generate:types` — the
  OpenAPI-Types CI check rebuilds TS from the committed spec, so a stale spec fails CI.
The Lead merges all branches onto `{integration_branch}`, runs ONE CI cycle, and opens ONE PR.

The Task* tools may be deferred — load them first via ToolSearch("select:TaskList,TaskUpdate")
if you need them. Claim your task with TaskUpdate(owner="worker-{TICKET}").

REPORTING IS NOT OPTIONAL: your plain-text output is INVISIBLE to the lead — you MUST call the
SendMessage tool. When the dev work is done (or a blocker stops you), send EXACTLY ONE message:
  SendMessage(to="team-lead", summary="worker-{TICKET} done|blocked",
              message="<branch: {branch-name} | commits: N | gates: lint ✓ types ✓ tests ✓ |
                        AC-check: clean|N findings (summary) |
                        blockers: none|{reason}>")
NEVER report done without a pushed branch. Even if you stop early, send the message first, then
mark your task completed via TaskUpdate.
```

The Worker-Brief deliberately carries rules inline that references also own (fast-gates
rule, test discipline, reporting contract) — workers run without plugin context and cannot
follow references. This is the one legitimate duplication (`plugin-authoring.md` § Single
owner); when a rule changes, update the owner AND this brief.

**Executor selection — three backends (select per chunk at the rolling confirm):**

Read `.weside/config.json` at boot: `tools.codex`, `execution.default`, and whether engine profiles exist in `.weside/engines.local.json`.

| Backend | When available | How dispatched |
|---|---|---|
| **Cheap Claude** (Sonnet/Haiku) | Always — the default | `Agent(model="sonnet", ...)` with the Worker-Brief above |
| **Codex** (`gpt-5-codex`) | `tools.codex: true` + user confirms per chunk | `codex-companion.mjs task` (see [`references/codex-dispatch.md`](../../references/codex-dispatch.md)) |
| **Foreign engine** | Engine profile in `.weside/engines.local.json` | `we/scripts/worker-launch.sh --engine <name> --cwd <worktree> -- <brief>` |

At the rolling confirm (Step 7+ or Step 3), offer the available backends. The **default is always cheap Claude** — an empty/ambiguous answer stays on Claude. Codex and foreign engine only run on an explicit per-chunk pick. Never auto-route or make the choice sticky across chunks without re-confirming.

**Only an Agent teammate can be steered mid-flight. Budget for that when you pick.** The
Worker-Brief's `SendMessage` contract and Step 7's "nudge the builder, at most once" describe
the **Agent** path. A Codex or foreign-engine worker is a detached process with no inbound
channel: once dispatched, nothing you learn can reach it. So on those backends the brief is
your only instrument, and every correction lands at integration instead.

Two practical consequences:

+ **Front-load everything into the brief** — the constraint you would otherwise have sent at
  minute ten (a namespace assignment, a seam you just discovered, a file it must not touch)
  has to be in the text before dispatch.
+ **Convert what you cannot say into what you will check.** A rule you cannot enforce mid-flight
  becomes a merge-time audit: write down, at dispatch, the exact command that will verify it.
  This is not a downgrade — a verified constraint beats an unverified message either way.

Prefer an Agent teammate when the work is genuinely exploratory (the shape may change under
the worker and you will want to redirect); prefer Codex when the brief can be complete.

**For foreign-engine dispatch via worker-launch.sh:**

```bash
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$0")")")"  # or $CLAUDE_PLUGIN_ROOT
bash "$PLUGIN_ROOT/scripts/worker-launch.sh" \
    --engine <profile-name> \
    --cwd <chunk-worktree-path> \
    -- "<Worker-Brief text>"
```

Brief format for headless dispatch: [`references/worker-dispatch.md`](../../references/worker-dispatch.md) § Foreign-engine brief format.
Single-detach rule: pass `run_in_background: true` in Bash (or omit for foreground). Never combine with a companion `--background` flag.

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

Two lanes, one loop. Re-run `story ready <epic>` on every pass — the buckets are the loop state,
never a cached list.

**Build lane (consumer).** Fill to the ≤2 cap from **`ready − in_flight`** (Step 2: the function has
no notion of "dispatched", so the set is yours to hold), taking the lowest-key story that is
**disjoint** from every in-flight build (guard below). Not disjoint → hold it *and stop filling*;
busy-picking past a blocked story just dispatches the collision you were avoiding.

**Refine lane (producer).** One story ahead, no deeper — the buffer throttle is
`refined-but-not-built < cap+1`. Take the lowest-key `refinable` story and refine it: **with the
user** when it needs a design call, **by the Lead alone** otherwise. (P3's Write-only
refiner-teammate takes this slot instead, but only after a rehearsal GO — it is off by default.)
Then re-run `story ready`: a story that left `refinable` enters the build lane next pass; one that
didn't gets one retry, then its blocker surfaced.

**Drain on events.** Builder done → review its PR (Step 8), recompute, refill. Refiner done → the
**Lead** runs `story ready` to verify (the body scan is what moves a story, not any claim of
"done"), then writes `story checkpoint {KEY} refined` and commits the plan.

**Terminate** when no ready story is dispatchable, `refinable` is empty, and nothing is in flight —
report the held set with reasons. Otherwise wait for the next event; **idle is not done**, so never
nudge on idle alone.

**The disjoint guard (a hint, not a guarantee).** Before dispatching a ready story while another
build is in flight, check file overlap: union each story plan's per-phase `**Files:**` lists and
set-intersect the to-dispatch story's union against each in-flight build's union; non-empty → **hold
until the conflicting build lands**. Be honest about its limits — cross-story file lists are coarse
(the plans were authored independently), a shared *seam* (the `select_responders`/`pending` case —
same function, not an obviously-shared filename) is invisible to a naive intersection, and the Lead
cannot see a builder's *uncommitted* edits. **When in doubt, serialize** (the Mode B rule): missing
file lists, any detected overlap, or any doubt → surface it in the rolling confirm ("PROJ-X and
in-flight PROJ-Y may both touch `select_responders.py` — dispatch or hold?") and default to hold.
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

### Step 8: Integrate finished branches + review + CI

**Two distinct phases — MERGE first, PR second. Never open a PR while workers are still running.**

#### Phase A: Merge (per worker, as each reports done)

**A1. Verify the worktree actually changed** before integrating — `git -C <worktree> status` / `git log`.
A worker reporting success with no commits signals a lost dispatch. Re-dispatch before integrating; never integrate an empty worktree.

**A2. Merge onto the integration branch — inside the integration worktree.** The integration
worktree (`$INT_WT`) was created in Step 4 before any worker was dispatched. Merge each finished
worker branch here as it arrives — do not wait for all workers to finish first. Run every command
in `$INT_WT`, never flip the main worktree:

```bash
git -C "$INT_WT" merge feat/<TICKET>-work --no-ff -m "integrate: merge feat/<TICKET>-work"
git -C "$INT_WT" push origin feat/<epic-or-story>-integration
```

Resolve conflicts using the plan's Constraints and Pins as the source of truth. Surface any
non-trivial conflict to the user before merging.

If a worker reported blocked, surface the blocker — do not silently merge empty or half-done work.

#### Phase B: the integration pipeline (once — only after ALL workers are merged)

Wait until every in-flight worker has either merged or been declared blocked. Then run
[`references/integration-pipeline.md`](../../references/integration-pipeline.md) **once, over the
merged diff** — simplify → AC+DoD gate → verification → parallel gates → docs → PR → one CI pass
→ tickets to In Review. That file is the owner of those steps; what follows is only what an
orchestrated run does differently.

**B0. Sync onto `main` first if it has drifted.** A long run lets `main` advance after Step 4 cut
the integration branch. From the integration worktree, `git -C "$INT_WT" fetch origin` then
`git -C "$INT_WT" merge origin/main` (preserve history), so the PR diff is **only this work** and
no stale-base check fails for a reason that has nothing to do with the wave. A diff-vs-main that
looks unexpectedly large is the drift tell — merge main, then re-read it.

**B1. The gates see the combined diff, and that is the point.** Every worker was green alone;
merge-combined import edges, duplicated keys and colliding exports appear only here. The
install-gated frontend gates the workers skipped (no `node_modules` in a fresh worktree, Step 6's
brief) run in the integration worktree — it is the one place in the run that can afford the
install. The reasoning and the cost of skipping it live in the pipeline reference.

**B2. Verification covers the journeys *the wave* claims** — not every AC of every story. One
walkthrough that crosses three merged stories is worth more than three that each stop at their
own seam. Findings here are integration findings: fix them on the integration branch, never in a
worker branch (those are done). A wave that cannot be verified does not open a PR.

**B3. The bug-hunt is writer-aware across the whole wave.** Every merged chunk written by Claude
with `tools.codex: true` → `/codex:adversarial-review`; any chunk from Codex or a foreign engine
→ Claude's native `/code-review`. The matrix is `worker-dispatch.md` § Bug-hunt dispatch.

**B4. Tickets: every Story that landed in this run** moves to In Review, not just the one that
finished last. This was half of a real regression — the PR existed while every ticket still read
"In Progress", because nothing owned the move once workers stopped doing it.

**The Lead writes the checkpoints, not the workers** — workers run `/we:develop`, which writes no
`story_workflow` rows at all. Confirm with `story status {TICKET}` before claiming a story shipped.

**CI red after the one pass:** report it and stop. The user decides whether to run
`/we:ci-review {PR}` again. This is the second human gate — surface the PR; the Lead never merges.

### Step 9: Final roll-up + close the team

Emit the final roll-up (shipped-to-review / blocked / held-by-cap).

If held stories exist (e.g. `waiting on PROJ-141`): **announce the next run explicitly.** The
`pr_created` checkpoint on PROJ-141 (written in Step 8 B2) immediately unlocks the held stories
in the ready-set — re-running `/we:orchestrate <epic>` after the PR is opened (no need to wait
for human merge) will pick them up. Tell the user this so the Epic progress stays visible:
> "PROJ-142 and PROJ-145 are ready for the next run — `/we:orchestrate PROJ-140` once the PR is open."

Then tear down the workers — run the **full teardown sequence** from
`${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md` § Full teardown (shutdown message to every
member → verify termination → `TaskStop` fallback → tmux pane check). Always tear down, even on
failure paths — a leaked worker blocks the next run in this session.

Then remove the Lead's integration worktree — it has done its job once B3 pushed
(`git worktree remove "$INT_WT"`; `git worktree remove --force "$INT_WT"` if it reports the tree
dirty). Leave the integration **branch** in place — the open PR points at it. On a run that ended
with held stories (the next `/we:orchestrate` resumes this branch), **keep** the worktree so the
resume path reuses it. Never remove the main worktree.

**Kill the worktree's own processes BEFORE you remove it — a removed worktree orphans its
servers, it does not stop them.** B1d's verification starts a dev server (and possibly a browser
driver) inside the integration worktree, and those ports are single-owner for the whole workspace.
Remove the directory without stopping them and the process survives with a deleted working
directory, still holding the port, and — if the run also pruned its database fork — serving a
schema that no longer exists, so every read answers 500. The next wave then loses the port at
exactly the moment it needs to verify, and the failure reads like a broken app.

```bash
# before `git worktree remove`: stop what this worktree started, BY PID
ss -ltnp 2>/dev/null | grep -E ':8000|:8081'            # ports are repo-specific; read them from the repo
ls -l /proc/<pid>/cwd                                    # a `(deleted)` target = an orphan from an earlier run
kill <pid>                                               # never `pkill -f <pattern>` — it self-matches
```

The same check is the diagnostic in the other direction: at the **start** of a run, a taken
single-owner port whose owner's `cwd` reads `(deleted)` is a leftover, not a live neighbour, and
is yours to clear. A taken port with a live cwd belongs to another session — coordinate, never
kill.

---

## Mode B — Lead-integrated phase dispatch (one coherent change, many phases)

**This is the execution path for a single-Story target** (Step 0 resolved one Story, not an epic) —
you arrive here directly from Step 1's shortcut. It is **also** reachable from an epic run when one
ready Story is really a phased coherent change (Step 3's mode choice). Either way the shape is the same.

The Step 1–9 workflow dispatches **one builder per Story** — right for independent, sprint-sized
slices, wrong for **a single coherent change split into phases** (a refactor, a migration), where N
full builds would pay the entire QS cost N times over. Keep such a change one Story; Mode B runs its
phases as lead-integrated chunks.

**The phase decomposition comes from the plan, not improvised.** `/we:story` already wrote the
`### Phase` blocks (with per-phase `**Files:**`) and the `parallel_groups` frontmatter — read them as
the chunk plan and the parallel-wave map. A group in `parallel_groups` is a wave of disjoint chunks
the Lead dispatches together (still ≤2 concurrent); phases outside any group are serial. Re-run the
parallelism discriminating check below before each wave — the plan's `parallel_groups` is a strong
hint, not a licence to skip the disjointness check.

Even a **small monolith** is a legitimate Mode-B target: the caller keeps their own context clean
and reviews the result neutrally. `/we:story` recommends this over `--solo` whenever the work is
more than trivially straight-line. The shape:

+ The Lead holds the **one** Story/Epic **and its phase decomposition** (the Lead already cut it into
  phases — that *is* the overview it holds).
+ Dispatch the phases as **lead-held work-chunks (tasks, not Stories)** via `TaskCreate` +
  `Agent(name=…)`. Teammates do **focused implementation only** — **not** the full
  the integration pipeline, **not** a per-chunk PR. Their brief is scoped to exactly one chunk.
+ Each teammate works its chunk in its own worktree, runs its **targeted** tests, and reports to the
  Lead via `SendMessage`.
+ The Lead **reviews each diff and integrates it onto one integration branch** — holding the thread,
  reading reports (not full transcripts) to keep its own context clean.
+ The heavy QS runs **once, at the end, by the Lead**: full suite + arch gates + AC-review
  (`we:ac-reviewer`, gating) + bug-hunt (writer-aware — Codex adversarial or native `/code-review`,
  see Step 8 B1a/B1b) + `/we:docs` + bypass register, then **one PR** for the whole change.
+ **Characterization-as-contract.** The first chunk writes a characterization net that pins current
  behaviour (green on unmodified code); every later chunk must keep those assertions **unchanged** —
  editing one is a deliberate, reviewed behaviour change, never a silent diff. The integration QS
  asserts they still pass. This is the no-regression guarantee that lets the change land as one cut.
+ Same guards as Mode A: the ≤2-concurrent cap, the confirm-to-dispatch gate, Lead-reviews, and
  **human merges**. Risk-driven order: a serial foundation chunk that **freezes the interface** first,
  then the disjoint chunks in parallel, then a final integration chunk the Lead owns.

**Choosing the mode (Step 3).** Independent ready Stories → the per-Story full-build workflow (Mode A).
One ready Story that is really a phased change the Lead has decomposed → this lead-integrated mode
(Mode B). When in doubt, ask the human which shape the work is.

### Chunk executor (Mode B)

A Mode-B chunk runs `/we:develop` — the same three backends as the Mode A dispatcher
(Step 6). The selection, verification, and dispatch mechanics are identical: see the
**Executor selection** block in Step 6 above.

**Mode B specific:** each phase-chunk gets its own worktree, branches off the integration
branch. The brief scopes `--phases` to the chunk's phase numbers. The Lead integrates phase
branches in plan order (serial for dependent phases, parallel for declared `parallel_groups`),
then runs CI once on the integration PR.

### Mode B field lessons (mandatory read before dispatching chunks)

Read [`references/mode-b-lessons.md`](references/mode-b-lessons.md) **before the first chunk dispatch**
— it carries the hard-won detail behind the Mode B rules below: the parallelism discriminating check
(shared scaffolding = serial foundation chunk; re-check at every wave boundary), worktree hygiene
(teammate worktrees off the integration branch, Lead never flips the main worktree), chunk-brief
discipline (mid-tier model default, surface forks before pinning, pins capture existing behaviour
only), and chunk review (green is the start of review, validate the integrated tree at full scope,
Lead owns cross-cutting glue, confirm the worktree root before trusting a green).

---

## `--solo` — one Story, nothing dispatched

The Lead implements the story itself and then runs the integration pipeline. No teammates, no
integration branch, no Agent-Teams flag: a plain feature branch in a worktree, the phases run in
this session, and the same pipeline at the end.

**Reach for it when dispatch buys nothing** — a single straight-line phase, a config change, a
one-function fix. Anything you would want to split into phases, or keep off your own context,
is Mode B: the phases go to chunk-workers and you keep the overview. `/we:story` already makes
that recommendation at the end of refinement; follow it rather than re-deciding here.

The shape:

1. **DoR** — load the ticket **and its comments** (`ticketing.md`), read the plan and every file
   it names, run the 3-item scan from `${CLAUDE_PLUGIN_ROOT}/references/dor-scan.md`. Failing
   scan → stop and name the missing item; `/we:story {TICKET}` is the fix, not a guess here.
   A plan older than the code it plans is the other stop condition: check its date against recent
   changes to the files it names, and re-refine rather than build against a plan that has been
   overtaken.
2. **Worktree + ticket** — `EnterWorktree(name="{type}/{TICKET}-short-description")`, ticket to
   In Progress, checkpoint `git_prepared`.
3. **Implement** the plan's phases in order, committing per phase. `parallel_groups` in the
   frontmatter names phases that may run as concurrent `Agent()` sub-tasks — at which point you
   are doing Mode B by hand and should have said so; honour it, and note it for next time.
   Checkpoint `implementation_complete`.
4. **[`references/integration-pipeline.md`](../../references/integration-pipeline.md)** for
   everything after that.

**Don't ask the user how to run it.** By the time a plan exists and they invoked this, the
decision to build is made — size and phase count are not negotiation levers. The four things
still worth interrupting for: the circuit breaker after three failures in one phase, the AC+DoD
gate (blocking by design), a named gap in the plan that reading the code cannot close, and
anything destructive. Everything else: execute.

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

The steps above are the spec — these are the invariants that are easiest to miss:

+ **Workers implement and stop** — `/we:develop`: implement + local gates + commit + push. The
  integration pipeline is the Lead's alone; a per-worker PR or CI run voids the single-CI contract
  the integration branch exists for.
+ **Spawn teammates with `Agent(name=…)`, all in one message — never `Skill()`** — there is no
  `team_name` parameter; workers join the session's implicit team just by being spawned.
+ **Never inject Companion identity into workers** — user-scoped `select_companion` race; only
  the Lead carries a voice. Fail loud on the env-flag, degrade gracefully on identity.
+ **The Lead owns ticket state** — "In Progress" at dispatch (Step 6), "In Review" after the
  integration PR + ci-review pass (Step 8 B4), never "Done". Verify each move, retry once,
  soft-fail loud only on workflow/permission rejection.
+ **Lead reviews, never merges** — Deliver (merge, close ticket, move to Done) is the human's job.
+ **Always tear the team down** (`references/agent-teams.md` § Full teardown) — even on failure
  paths.

Mode-B chunk discipline (parallelism check, worktree hygiene, brief forks, integrated-tree
validation) lives in `references/mode-b-lessons.md` — the mandatory read before chunk dispatch.
The `--refine-ahead` invariants (buffer throttle, disjoint guard, termination predicate, P3
single-writer rule) are specified inline in Step 7+ and `references/refine-ahead-p3.md`.

## References

+ `${CLAUDE_PLUGIN_ROOT}/references/integration-pipeline.md` — everything after implementation: simplify, AC+DoD, verification, gates, docs, PR, CI
+ `references/worker-dispatch.md` — worker contract, three backends, AC-review rule, bug-hunt dispatch, integration-branch/single-CI
+ `references/codex-dispatch.md` — Codex single-detach rule + chunk-brief template
+ `we/scripts/worker-launch.sh` — foreign-engine launcher (reads `.weside/engines.local.json`)
+ `references/mode-b-lessons.md` — hard-won Mode B field lessons (mandatory read before chunk dispatch)
+ `references/refine-ahead-p3.md` — the autonomous refiner lane (off by default) + Refiner-Brief
+ `references/rehearsal.md` — `--rehearsal` procedure + P3 go/no-go
+ `references/fixture-story.md` + `references/fixture-refinable-story.md` — rehearsal fixtures
+ `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md` — env-flag prerequisite + full teardown
+ `we/skills/council/SKILL.md` — the Agent-Teams machinery this skill mirrors
+ `we/skills/develop/SKILL.md` — the dev-only worker skill workers run
+ `scripts/orchestration.py` — `story status|list|checkpoint|ready` (tracking + ready-set)
+ `scripts/test_ready_set.py` — unit tests for the `compute_ready_set` pure helper
