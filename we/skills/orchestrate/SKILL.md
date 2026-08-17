---
name: orchestrate
description: >
  The Lead for a story or an epic — reads state from git, refines what has no
  plan, dispatches dev workers for what does, integrates their branches, and
  runs CI once on one PR. Use when the user says "/we:orchestrate", "orchestrate
  the epic", "orchestrate this story", "dispatch the ready stories", "run the
  phases".
---

# /we:orchestrate

**Purpose:** stop being the manual courier between a planning session and per-Story build sessions.
The Lead — the session running `/we:orchestrate` — is a persistent colleague that boots knowing
where the work stands, holds context, decides what each story needs next, dispatches it, integrates
what comes back, and reviews the combined diff. CI runs **once** on the integration PR, not once per
worker. It never merges — Deliver stays human.

**Cost model:** dev workers run on cheap-tier Claude (Sonnet/Haiku), Codex, or a foreign engine;
**refiners run on Opus** — the plan is the one artifact every later worker follows (model-tier rule:
[`references/worker-dispatch.md`](../../references/worker-dispatch.md)). The
Lead (the expensive session model) plans, integrates, and reviews. N workers = N dev costs + one
integration CI, not N full pipelines. A story too small to be worth a worker runs `--solo` — same
pipeline, nothing dispatched.

> **One pipeline, three dispatch shapes.** Every run ends the same way: implement → simplify →
> AC/DoD gate → **verification** → quality gates → docs → PR → one CI pass. That half is owned by
> [`${CLAUDE_PLUGIN_ROOT}/references/integration-pipeline.md`](../../references/integration-pipeline.md)
> and is identical whether the code came from one worker, five, or the Lead's own hands. What
> differs is only *who implements*: workers per Story, workers per phase (Mode B), or nobody
> (`--solo`).

This is the **Build-altitude sibling of `/we:council`/`/we:meet`**: the same Agent-Teams machinery
(spawn into the session's implicit team via `Agent(name=…)` → `SendMessage` → shutdown-message
teardown), but the teammates are **dev workers** running `/we:develop` and **refiners** running
`/we:refine`, not deliberators.

**The stance (not just the mechanics).** The Lead is a *persistent partner*, not a throwaway
dispatcher. It boots knowing where the work stands, **holds the overview so the human is not
overwhelmed**, plans and assigns the work, and integrates and evaluates what comes back. The human
is good at saying *where we want to go*; the Lead carries it *on the way* — that continuity, someone
holding the whole across the dispatch loop, is the point. When a Companion is materialized, the Lead
is that Companion (warmth + presence, not manager-speak), not a generic dispatcher.

**Forward momentum, gated.** The Lead's default state is *working toward the merge*, and its
communication serves that:

+ **A waiting Lead is a bug.** While CI or a review round runs, fill the refine lane, prepare
  the next wave's briefs, or build the next Lead-owned unit — and name what you are working on
  during the wait. "Waiting for CI" is never the whole answer.
+ **Critical-path test before non-gate work:** does this pull the merge forward? Gates, reviews
  and tests are the critical path; extra prose, a third safeguard on an already-green fix, and
  nice-to-have docs are not — they go behind the merge.
+ **Status answers are three parts, ≤5 sentences:** what stands (one line per open item), what
  the human must do (usually: nothing), what the Lead does next. History, tables and how-it-came
  explanations only on request.
+ **Intermediate states go to the state file, not the chat.** The human hears from the Lead at
  wave boundaries, at the Decision Queue, and when a gate needs them — not per step.

None of this loosens the gates — it sharpens them. The human still approves plans before their
build (Step 4), still gets every PR surfaced, still merges, and still owns every Step-3 signal.
Momentum never skips a gate; **at a gate, stop fully and ask crisply** — a well-formed question
with a recommendation is faster for everyone than a hedged essay.

## Prerequisites

```
Read("${CLAUDE_PLUGIN_ROOT}/references/verification.md")
Read("${CLAUDE_PLUGIN_ROOT}/references/long-running.md")
```

Agent Teams must be enabled — same flag, abort text, and teardown contract as `/we:council`: see
`${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md`. No non-team fallback.

**Permission mode must allow teammate Bash — check before dispatch, not after.** A dev worker's job
is almost entirely Bash (git, gh, the orchestration CLI). Under the default/auto mode the classifier
denies *every* teammate Bash call, because a teammate-message-triggered invocation carries no direct
user intent: the worker is dispatched, reaches its first command, and is dead on arrival with "Bash
denied" and nothing written. So the session must be on **`acceptEdits`** (or bypass), or carry a Bash
allowlist for the multi-agent path. Surface this at the confirm gate; if you cannot tell the mode,
ask. **Refiners are unaffected** — `/we:refine` writes a file and runs nothing, which is exactly why
it is shaped that way. `--solo` needs none of this: it dispatches nothing.

## Invocation

```
/we:orchestrate <epic>                 # epic target: state + next actions; dispatch on confirm
/we:orchestrate <story-key>            # single-Story target: run THIS story's phases as work-chunks (Mode B)
/we:orchestrate <story-key> --solo     # single Story, no workers: implement here, then integrate
/we:orchestrate <epic> --rehearsal     # run the pipeline against a fixture, no real PR/ticket
/we:orchestrate                        # boot from the most recently active epic, then status
```

### Target resolution (Step 0 — do this before booting)

The argument is either an **Epic** or a **single Story**. Resolve it once, it picks the whole shape:

+ **Single-Story target** when the argument matches a Story plan `docs/plans/{KEY}-story.md` (or its
  ticket key resolves to one Story) AND there is no Epic plan / no other story shares it as an
  `epic:`. → **Skip the state read** and run **Mode B** over that one plan's `### Phase` blocks.
  Honour the plan's `parallel_groups` for the parallel waves.
+ **`--solo`** forces the single-Story shape and skips dispatch entirely — see the `--solo` section
  below. It is the only flag that changes *who implements*.
+ **Epic target** otherwise (an Epic plan exists, or ≥1 story shares the slug/key as `epic:`).
  → the full Step 1–9 workflow; one story in the wave may itself run Mode B.

`<epic>` is an Epic **slug** (e.g. `circles`) or a ticketing Epic key (e.g. `PROJ-1205`) — either
works. Stories may reference their epic by slug or by key; the state CLI resolves both via the Epic
plan's `epic:`/`ticket:` frontmatter.

---

## Workflow

### Step 1: Boot from state (always — this is the colleague's first act)

> **Single-Story target shortcut.** If Step 0 resolved a **single Story**: read just that one plan
> completely + `orchestration.py story status {KEY}` + any recent handoff, render a one-line stand,
> then jump to the confirm gate and Mode B (or `--solo`).

**Read the wave journal first.** An epic that spans waves keeps `docs/plans/<epic>-state.md` — the
FIRST thing read and the LAST thing written in every run. It carries what git cannot: which
decisions were made, what was tried and rejected, which worker was dispatched where. If it does not
exist and the epic spans more than one wave, creating it is the run's first act. Programme-scale
shape (living plans, self-verification, the `/loop` form):
`${CLAUDE_PLUGIN_ROOT}/references/programme-discipline.md`.

Then reconstruct "where we stand" from the **living** files — never from cached knowledge:

1. **Epic frame** — the Epic plan `docs/plans/*<epic>*-epic.md`; its `## Success Criteria` and scope
   are the lens for "what done means". No epic file and no mirror row → **degrade gracefully**:
   synthesise the frame from the child Stories sharing this `epic:` slug. An epic backed only by
   Story plans is valid (a rehearsal, or a freshly cut epic).
2. **State** — Step 2, one command.
3. **Ticketing** — fetch each Story's ticket status **and its comments**; comments carry corrections
   and scope cuts the plan file may predate, newest statement wins on conflict, and you name the
   conflict (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`). This is also where three of the five
   human signals come from (Step 3). No ticketing tool → plan frontmatter `status` only.
4. **Handoff** — a recent `docs/handoffs/` entry for this Epic carries decisions the files don't.

Render a tight **"here is where we stand"** snapshot, then **stay open** as the conversational
partner. If the user only asked status, present it and **wait** — do not dispatch without an
explicit go.

### Step 2: Read the state (evidence, not bookkeeping)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story state <epic> \
  --plans-dir docs/plans --in-flight "{keys you dispatched this session}" \
  [--base <ref>] [--integration-branch <branch>]
```

Every story lands on exactly one rung. **The first matching rule wins**, which is why the order is
load-bearing: a shipped story is never asked whether it was planned, and a merged branch outranks a
checkpoint nobody wrote.

| State | Evidence | Next action |
|---|---|---|
| `shipped` | ticket in review/done/merged, or a `pr_created`/`ci_passed` checkpoint | — |
| `integrated` | the story branch is an ancestor of the integration branch | wait for the wave to close |
| `built` | a story branch exists with commits beyond the base | **INTEGRATE** (Lead, serial) |
| `refined` | the plan passes the DoR scan | **DEVELOP** (worker, ≤2) |
| `draft` | a plan file exists but fails the scan | **REFINE** (worker, ≤3) |
| `idea` | only a mirror row or a ticket | **REFINE** (worker, ≤3) |

The CLI returns `dispatch` (the three lanes, already capped), `decisions`, `waiting` (each with a
reason), and a row per story. The table is the spec, the CLI is the implementation — they must not
drift.

**Git is asked first because it cannot forget.** A checkpoint exists only when someone remembered to
write it; a branch exists because work happened. On 2026-07-28 four merged stories read as unbuilt
for exactly that reason and the Lead kept re-offering them. Where git cannot answer — no repo, no
resolvable base, a branch that hides the ticket key — the CLI falls back to checkpoints on its own.

**`refined` is also a signal, not only a rung.** A story that shipped without a plan comes back with
`built-without-plan`, because the integration gate then has no acceptance criteria to verify against.
Don't let the ladder swallow it: name it in the roll-up and decide whether the wave can honestly gate.

**The CLI cannot know what you dispatched — a dispatch is not an outcome.** That is why
`--in-flight` exists and why the Lead holds that list. Two places it bites:

+ A freshly refined story entering the develop lane displaces a dispatched one in the cap accounting
  unless you pass it in.
+ **On a resumed run** (after a compact, a new session, a crash) the state read is all you have, and
  it will happily offer a story whose worker is still running. Before dispatching anything on a
  resume, check for its branch and worktree (`git worktree list`,
  `git branch --list 'feat/{KEY}-*'`) and treat either as in-flight.

### Step 3: The five human signals — which unplanned stories a worker may not take

A refiner can write a plan from front-loaded context. It cannot make a decision that was never made.
Before putting a `draft`/`idea` story in the refine lane, check these five against evidence you can
point at. **Any one of them fires → the story goes to the Decision Queue instead of a worker.**

1. **An open question in the ticket** — a question mark in summary or description, or a comment
   asking for a decision that has no answer under it.
2. **The epic plan names it and nothing more** — no sentence in Scope or Sequencing that says what
   it covers. ("Rooms hardening" — hardening *what*?)
3. **A caveat in the mirror notes** — `TBD`, `open`, `unclear`, `needs decision`, `blocked on`.
4. **It freezes an interface others consume** — the epic plan describes it as a foundation or the
   first of its kind. Those go first and go serial; a plan written against a seam that is still
   moving is rework with a timestamp.
5. **Comments contradict the description** — newest wins, and the conflict gets named rather than
   silently resolved (`ticketing.md`). If the newest statement changes scope, that is a decision,
   not a detail.

None fires → the context is front-loadable → dispatch a refiner, and pass what you checked as the
brief's context block. That check *is* the front-loading.

### Step 4: The Decision Queue — batch, don't interrupt

Everything that needs the human — scope questions from Step 3, design forks a worker reported,
whether to cut a staging RC, **and the finished plans waiting for approval** — is collected and put
in front of them **as one batch at the wave boundary**. Not mid-loop, not per story.

`programme-discipline.md` § 5 states the arithmetic: many stories × open questions ÷ one human is
the real bottleneck. Interrupting per story converts the Lead's parallelism into the human's queue.

**Refined plans are approved in the batch, before their build starts.** A plan is the specification
— a wrong plan produces correctly-built wrong code, the most expensive failure in the chain and the
only one whose cost stays invisible until integration. Two to four plans at a time is the readable
size; beyond that the review stops being real.

This is the first of three human gates. The others: the Lead surfaces each PR (Step 8), and the
human merges.

### Step 5: Preflight

1. **Env-flag check** — confirm `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`; if missing, abort with the
   remediation hint from `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md`.

2. **Concurrency caps (refine ≤3, develop ≤2, integrate serial)** — refine is the cheap lane: no
   worktree, no Bash, no collision surface, so three run comfortably. Develop is the expensive one.
   **The Lead may raise the develop cap** when the work is demonstrably disjoint and the context can
   hold it — state the reason explicitly before doing so. A raised cap with uncertain disjointness is
   a judgment call; when in doubt, keep the default.

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

3. **The disjoint guard (a hint, not a guarantee).** Before dispatching a develop worker while
   another build is in flight, union each plan's per-phase `**Files:**` lists and intersect them.
   Non-empty → **hold until the conflicting build lands**, and stop filling the lane rather than
   busy-picking past it. Be honest about its limits: cross-story file lists are coarse, a shared
   *seam* (same function, different filenames) is invisible to a set intersection, and you cannot
   see a worker's uncommitted edits. **When in doubt, serialize** — or surface it in the confirm
   ("PROJ-X and in-flight PROJ-Y may both touch `select_responders.py` — dispatch or hold?").

4. **Lead voice (MCP, optional)** — if `mcp__plugin_we_weside-mcp__get_council` exists, call it once
   for the Lead's review role (`product_owner` or `architect`, per `.weside/config.json`) and adopt
   that Companion's `identity_prompt` for the Lead's review voice in Step 8. Teammates get **no**
   identity (the weside backend is user-scoped — parallel `select_companion` races; see
   `/we:council` "Memory in v1"). No MCP → generic review lens. Degrade gracefully.

5. **Create the integration branch in a dedicated worktree** — NOW, before any worker is dispatched,
   so every worker has the same base. Workers branch off the pushed ref; the Lead merges their
   branches back here; the final PR runs against it.

   **The Lead never flips the *main* worktree's branch** — it stays on the default branch, untouched,
   for the whole run. Flipping it lands commits on the wrong branch and lets a stray rebase rewrite a
   worker's pushed branch; that is a real, repeated failure mode. Instead the Lead integrates from a
   **dedicated integration worktree** as a sibling of the repo
   (`$(git rev-parse --show-toplevel)-integration`), and every integration command runs inside it via
   `git -C`. It is also the one place in the run that can afford a dependency install.

   On a resumed run, **never reset an existing branch or worktree**: reuse the worktree if it is
   there, add one onto the existing branch if only the branch is, and create both plus an upstream
   push only on a genuinely fresh run.

### Step 6: Dispatch the wave (all spawns in one message)

The current harness gives every session one implicit team; there is no `TeamCreate` call and no
`team_name`. The Lead is the session that ran `/we:orchestrate`, and teammates become addressable
purely by being spawned with a `name`. **Put every spawn of a wave in a single assistant message** so
they initialize concurrently — refiners and dev workers together; they compete for nothing.

```python
# refine lane — Write-only, no worktree, no Bash; opus, per the model-tier rule
Agent(name=f"refiner-{TICKET}", subagent_type="general-purpose", model="opus",
      description=f"Refine {TICKET}", prompt=<Refiner-Brief>)

# develop lane — one worktree each, off the integration branch
TaskCreate(subject=f"Build {TICKET}", description=f"Run /we:develop for {TICKET} to a pushed branch.")
Agent(name=f"worker-{TICKET}", subagent_type="general-purpose", model="sonnet",
      description=f"Build {TICKET}", prompt=<Worker-Brief>)
```

The shared task-list carries the **live** dispatched state. The **durable** record is the Lead's to
write: workers run `/we:develop`, which writes no `story_workflow` rows at all, so every checkpoint
lands in Step 8 and nowhere else.

Two halves of the same regression sit behind that sentence, and both were expensive. When workers
moved from running the whole pipeline themselves to running dev-only `/we:develop`, nobody re-read
the paragraphs whose premise was "the worker does X": tickets stopped moving out of "In Progress",
and — unnoticed for longer — checkpoints stopped being written, so stories that had shipped and
merged still read as **unbuilt** and the Lead kept re-proposing them. **When a dispatch mode changes,
re-read every paragraph whose premise is what the worker does — not only the ones that name it.**

**Transition each dispatched Story → "In Progress" now (Lead owns this — workers do NOT).** If the
Lead doesn't move the ticket, nothing does. Detect the tool per
`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`, **verify** the move, retry once, soft-fail loud only
when the workflow rejects it. GitHub Issues / no ticketing tool → skip silently.

#### Refiner-Brief

```
You are refiner-{TICKET}, a teammate spawned into this session's implicit team. The lead is "team-lead".

Run: Skill(skill="refine") for {TICKET}. That skill is your instruction set — write
docs/plans/{TICKET}-story.md and report the path. Write only: no git, no gh, no orchestration
command, and never EnterPlanMode/ExitPlanMode — there is no human here to approve anything.

CONTEXT (front-loaded — this replaces the clarification a human would give):
  Epic frame:        {success criteria + scope, 3-5 lines}
  This story:        {ticket title + the one-paragraph intent}
  Scope boundaries:  {what is IN / explicitly OUT}
  Known constraints: {seams, deps, prior decisions, the files it will touch}
  Architecture refs: {the 1-3 docs/ files most relevant — read them before drafting}

If you hit a design fork this context cannot settle, do NOT guess — report the fork and stop.

REPORTING IS NOT OPTIONAL: your plain-text output is INVISIBLE to the lead. Send EXACTLY ONE message:
  SendMessage(to="team-lead", summary="refiner-{TICKET} done|blocked",
              message="wrote docs/plans/{TICKET}-story.md | blocked: <fork/reason>")
Do not verify your own plan and do not claim it passed — the Lead runs the scan.
```

**The Lead is the single writer and the only verifier.** On a refiner's report: re-run `story state`
(the body scan is what moves a story, not any claim of "done") → if it left `draft`/`idea`, queue the
plan for the batch approval in Step 4, then `story checkpoint {KEY} refined` and commit it → if it
failed, re-dispatch **once** with the specific missing item ("no `### Phase` header") → still
failing, it goes to the Decision Queue as `refine failed — needs human`. That split keeps
`docs/plans/` and `orchestration.db` single-writer on main, and it is what lets a refiner run with no
Bash at all.

#### Worker-Brief (self-contained — the worker runs dev-only `/we:develop`)

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

FINISH FIRST: a small finding (≤ ~30 min) on the seam you touch gets FIXED in your
branch — "pre-existing" alone is no deferral reason. Only product decisions, money-path
changes, and foreign-subsystem redesigns go back to the Lead — as QUESTIONS in your
report, never as new tickets. Workers never create tickets.

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
  dispatch, Step 8 after integration)
- DO NOT run the integration pipeline — no PR, no CI, no doc pass, no ticket transitions
- DO NOT run frontend gates (`yarn`/`npm install`, `jest`, `tsc`) in a fresh worktree — it has no
  `node_modules` (~1GB) and building them is wasted setup. Implement the frontend changes, run
  ONLY touched-stack unit tests that need no install, and REPORT the skipped frontend validation;
  the Lead runs those install-gated gates locally at integration, **before** the PR —
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

Both briefs deliberately carry rules inline that references also own (fast-gates rule, test
discipline, reporting contract) — a worker dispatched to a foreign engine has no plugin context and
cannot follow a reference. This is the one legitimate duplication (`plugin-authoring.md` § Single
owner); when a rule changes, update the owner AND the brief.

#### Executor selection — three backends (pick per chunk at the confirm)

Read `.weside/config.json` at boot: `tools.codex`, `execution.default`, and whether engine profiles
exist in `.weside/engines.local.json`.

| Backend | When available | How dispatched |
|---|---|---|
| **Cheap Claude** (Sonnet/Haiku) | Always — the default | `Agent(model="sonnet", ...)` with the brief above |
| **Codex** (`gpt-5-codex`) | `tools.codex: true` + user confirms per chunk | `codex-companion.mjs task` ([`references/codex-dispatch.md`](../../references/codex-dispatch.md)) |
| **Foreign engine** | Engine profile in `.weside/engines.local.json` | `we/scripts/worker-launch.sh --engine <name> --cwd <worktree> -- <brief>` |

The **default is always cheap Claude** — an empty or ambiguous answer stays on Claude. Codex and
foreign engines run on an explicit per-chunk pick; never auto-route, and never make the choice sticky
across chunks without re-confirming.

**Only an Agent teammate can be steered mid-flight. Budget for that when you pick.** The
brief's `SendMessage` contract and Step 7's "nudge the worker, at most once" describe
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

For foreign-engine dispatch, pass `run_in_background: true` in Bash (or omit for foreground) and
never combine it with a companion `--background` flag. Brief format:
[`references/worker-dispatch.md`](../../references/worker-dispatch.md) § Foreign-engine brief format.

### Step 7: Monitor + roll-up (Lead observes)

⚠️ **The two rules the Lead most often gets wrong — read them first, follow them literally:**

1. **Idle ≠ done. Never nudge on idle alone.** A worker running a full build idles repeatedly
   between turns; a contentless `idle_notification` is NOT a completion signal and NOT a problem.
   Wait for the worker's actual `SendMessage` — it can take many minutes of silence.
2. **State-as-truth.** Never make "is this Story done" depend on a message arriving. When you
   need to know a worker's state (long idle, ambiguous report, before any roll-up claim), run
   this checklist instead of guessing:
   1. `orchestration.py story state {EPIC}` — which rung is it on, and on what evidence?
   2. `git log` on the worker's branch — are commits landing?
   3. `gh pr checks {PR}` if a PR exists — what is CI *actually* saying?
   4. Only after 1–3: nudge the worker, **at most once**.

   **A wait condition may only watch state the WORKER changes.** Never anchor it
   on a branch the Lead moves while integrating: `until git log
   <integration-branch>..HEAD | grep -q .` goes permanently false for a worker
   whose branch you just merged, so the trigger can never fire and the Lead sits
   on an impossibility believing it is still waiting. Anchor on a fixed sha
   (`rev-list --count <sha>..HEAD`), a remote branch's existence, or a file only
   the worker writes. The bug appears precisely when the Lead integrates EARLY —
   which this skill recommends — so better integration makes it more likely, not
   less. Diagnosing it: `pgrep -af until` shows whether the wait still lives and
   what it compares against; a live wait on an unsatisfiable condition is this
   mistake.

Reports arrive by `SendMessage` (delivered automatically — do not poll a terminal) and via the
shared task-list. Emit a running roll-up:
`refining: {…} | building: {…} | to integrate: {…} | waiting: {…}`.

**Refill lanes on events, not on a timer.** A worker done → integrate it (Step 8), re-read state,
refill. A refiner done → verify, queue the plan for the batch. Re-read `story state` on every pass:
the rungs are the loop state, never a cached list.

**Terminate the wave** when nothing is in flight and no lane can be filled — then report the waiting
set with reasons. "Everything left conflicts with an in-flight build" is correct serialization, not
deadlock: a held story becomes dispatchable at the next integration. A `depends_on` **cycle** is not
detected by the state model and drains to this same predicate — name the cycle rather than waiting
forever.

### Step 8: Integrate finished branches + review + CI

**Two distinct phases — MERGE first, PR second. Never open a PR while workers are still running.**

#### Phase A: Merge (per worker, as each reports done)

**A1. Verify the worktree actually changed** before integrating — `git -C <worktree> status` /
`git log`. A worker reporting success with no commits signals a lost dispatch. Re-dispatch before
integrating; never integrate an empty worktree.

**A2. Merge onto the integration branch — inside the integration worktree.** Merge each finished
branch as it arrives; do not wait for all workers. Every command runs in `$INT_WT`, never in the main
worktree:

```bash
git -C "$INT_WT" merge feat/<TICKET>-work --no-ff -m "integrate: merge feat/<TICKET>-work"
git -C "$INT_WT" push origin feat/<epic-or-story>-integration
```

Resolve conflicts using the plan's Constraints and Pins as the source of truth. Surface any
non-trivial conflict to the user before merging. A worker that reported blocked gets its blocker
surfaced — never silently merge half-done work.

#### Phase B: the integration pipeline (once — only after ALL workers are merged)

Wait until every in-flight worker has either merged or been declared blocked. Then run
[`${CLAUDE_PLUGIN_ROOT}/references/integration-pipeline.md`](../../references/integration-pipeline.md)
**once, over the merged diff** — simplify → AC+DoD gate → verification → parallel gates → docs → PR →
one CI pass → tickets to In Review. That file owns those steps; what follows is only what an
orchestrated run does differently.

**B0. Sync onto `main` first if it has drifted.** A long run lets `main` advance after Step 5 cut the
integration branch. From the integration worktree, `git -C "$INT_WT" fetch origin` then
`git -C "$INT_WT" merge origin/main` (preserve history), so the PR diff is **only this work** and no
stale-base check fails for a reason that has nothing to do with the wave. A diff-vs-main that looks
unexpectedly large is the drift tell — merge main, then re-read it.

**B1. The gates see the combined diff, and that is the point.** Every worker was green alone;
merge-combined import edges, duplicated keys and colliding exports appear only here. The
install-gated frontend gates the workers skipped run in the integration worktree — the one place in
the run that can afford the install.

**B2. Verification covers the journeys *the wave* claims** — not every AC of every story. One
walkthrough crossing three merged stories is worth more than three that each stop at their own seam.
Findings here are integration findings: fix them on the integration branch, never in a worker branch
(those are done). A wave that cannot be verified does not open a PR.

**B3. The bug-hunt is writer-aware across the whole wave.** Every merged chunk written by Claude with
`tools.codex: true` → `/codex:adversarial-review`; any chunk from Codex or a foreign engine →
Claude's native `/code-review`. The matrix is `worker-dispatch.md` § Bug-hunt dispatch.

**B4. Tickets: every Story that landed in this run** moves to In Review, not just the one that
finished last. This was half of a real regression — the PR existed while every ticket still read
"In Progress", because nothing owned the move once workers stopped doing it.

**The Lead writes the checkpoints, not the workers.** Confirm with `story status {TICKET}` before
claiming a story shipped.

**CI red after the one pass:** report it and stop. The user decides whether to run
`/we:ci-review {PR}` again. This is the second human gate — surface the PR; the Lead never merges.

### Step 9: Close the wave — journal, roll-up, teardown

**Write the journal before anything else.** `docs/plans/<epic>-state.md` gets one row per action
this wave — story, task, worker, branch, outcome, timestamp — plus the decisions taken and what is
still open. This is the resume anchor: after a compact or in a new session the Lead reads the journal
and derives the rest from git. Written last, it is the difference between resuming and reconstructing.

Then the roll-up: shipped-to-review / integrated / waiting, each with its reason. If stories are
waiting, **announce the next run explicitly** — the `pr_created` checkpoint written in Step 8 unlocks
them immediately, so re-running `/we:orchestrate <epic>` after the PR is open (no need to wait for a
human merge) picks them up:

> "PROJ-142 and PROJ-145 are ready for the next run — `/we:orchestrate PROJ-140` once the PR is open."

Then tear down every teammate — the **full teardown sequence** from
`${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md` § Full teardown (shutdown message to every member →
verify termination → `TaskStop` fallback → tmux pane check). Always tear down, even on failure paths
— a leaked worker blocks the next run in this session.

Then remove the Lead's integration worktree — it has done its job once the PR is pushed
(`git worktree remove "$INT_WT"`, `--force` if it reports the tree dirty). Leave the integration
**branch** in place; the open PR points at it. On a run that ended with waiting stories, **keep** the
worktree so the resume path reuses it. Never remove the main worktree.

**Kill the worktree's own processes BEFORE you remove it — a removed worktree orphans its
servers, it does not stop them.** Verification starts a dev server (and possibly a browser
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

## `--solo` — one Story, nothing dispatched

The Lead implements the story itself and then runs the integration pipeline. No teammates, no
integration branch, no Agent-Teams flag: a plain feature branch in a worktree, the phases run in
this session, and the same pipeline at the end.

**Reach for it when dispatch buys nothing** — a single straight-line phase, a config change, a
one-function fix. Anything you would want to split into phases, or keep off your own context, is
Mode B: the phases go to chunk-workers and you keep the overview. `/we:story` already makes that
recommendation at the end of refinement; follow it rather than re-deciding here.

The shape:

1. **DoR** — load the ticket **and its comments** (`ticketing.md`), read the plan and every file it
   names, run the 3-item scan from `${CLAUDE_PLUGIN_ROOT}/references/dor-scan.md`. Failing scan →
   stop and name the missing item; `/we:story {TICKET}` is the fix, not a guess here. A plan older
   than the code it plans is the other stop condition: check its date against recent changes to the
   files it names, and re-refine rather than build against a plan that has been overtaken.
2. **Worktree + ticket** — `EnterWorktree(name="{type}/{TICKET}-short-description")`, ticket to
   In Progress, checkpoint `git_prepared`.
3. **Implement** the plan's phases in order, committing per phase. `parallel_groups` in the
   frontmatter names phases that may run as concurrent `Agent()` sub-tasks — at which point you are
   doing Mode B by hand and should have said so; honour it, and note it for next time. Checkpoint
   `implementation_complete`.
4. **[`${CLAUDE_PLUGIN_ROOT}/references/integration-pipeline.md`](../../references/integration-pipeline.md)**
   for everything after that.

**Don't ask the user how to run it.** By the time a plan exists and they invoked this, the decision
to build is made — size and phase count are not negotiation levers. The four things still worth
interrupting for: the circuit breaker after three failures in one phase, the AC+DoD gate (blocking
by design), a named gap in the plan that reading the code cannot close, and anything destructive.
Everything else: execute.

---

## Mode B — phase dispatch (one coherent change, many phases)

**This is the execution path for a single-Story target** — you arrive here from Step 1's shortcut.
It is **also** reachable from an epic run when one story is really a phased coherent change.

The Step 1–9 workflow dispatches **one worker per Story** — right for independent, sprint-sized
slices, wrong for **a single coherent change split into phases** (a refactor, a migration), where N
full builds would pay the entire QS cost N times over. Keep such a change one Story; Mode B runs its
phases as lead-integrated chunks.

**The phase decomposition comes from the plan, not improvised.** `/we:story` (or `/we:refine`)
already wrote the `### Phase` blocks with per-phase `**Files:**` and the `parallel_groups`
frontmatter — read them as the chunk plan and the parallel-wave map. A group is a wave of disjoint
chunks dispatched together (still ≤2 concurrent); phases outside any group are serial. Re-run the
disjointness check before each wave — `parallel_groups` is a strong hint, not a licence to skip it.

Even a **small monolith** is a legitimate Mode-B target: the caller keeps their own context clean and
reviews the result neutrally. `/we:story` recommends this over `--solo` whenever the work is more
than trivially straight-line. The shape:

+ The Lead holds the **one** Story **and its phase decomposition** (that *is* the overview it holds).
+ Dispatch the phases as **lead-held work-chunks (tasks, not Stories)** via `TaskCreate` +
  `Agent(name=…)`. Teammates do **focused implementation only** — not the integration pipeline, not a
  per-chunk PR. Their brief is scoped to exactly one chunk, and it runs `/we:develop` on the same
  three backends as Step 6.
+ Each teammate works its chunk in its own worktree off the integration branch, runs its **targeted**
  tests, and reports via `SendMessage`.
+ The Lead **reviews each diff and integrates it onto one integration branch** — reading reports, not
  full transcripts, to keep its own context clean.
+ The heavy QS runs **once, at the end, by the Lead**: the integration pipeline, then one PR.
+ **Characterization-as-contract.** The first chunk writes a characterization net that pins current
  behaviour (green on unmodified code); every later chunk must keep those assertions **unchanged** —
  editing one is a deliberate, reviewed behaviour change, never a silent diff. The integration QS
  asserts they still pass. This is the no-regression guarantee that lets the change land as one cut.
+ Same guards as an epic run: the ≤2-concurrent cap, the confirm gate, Lead-reviews, human merges.
  Risk-driven order: a serial foundation chunk that **freezes the interface** first, then the
  disjoint chunks in parallel, then a final integration chunk the Lead owns.

Read [`references/mode-b-lessons.md`](references/mode-b-lessons.md) **before the first chunk
dispatch** — the parallelism discriminating check, worktree hygiene, chunk-brief discipline, and why
green is the start of chunk review rather than the end.

---

## Rehearsal mode (`--rehearsal`)

Run the complete pipeline against a committed fixture instead of a real epic — the lab for shaking
out skill bugs. Full procedure: [`references/rehearsal.md`](references/rehearsal.md).

## Standalone fallback

No weside account / no MCP → the Lead reviews with the generic role lens, workers run normally (they
never needed identity). Everything else is identical. The Agent-Teams env-flag is required regardless
of weside connection.

## Rules

The steps above are the spec — these are the invariants easiest to miss:

+ **Workers implement and stop** — `/we:develop`: implement + local gates + commit + push. The
  integration pipeline is the Lead's alone; a per-worker PR or CI run voids the single-CI contract
  the integration branch exists for.
+ **Refiners write and stop** — `/we:refine`: one plan file, one report. The Lead runs the scan,
  writes the `refined` checkpoint, and commits; a refiner that verifies its own output is a refiner
  whose failures are invisible.
+ **Spawn teammates with `Agent(name=…)`, all of a wave in one message — never `Skill()`** — there is
  no `team_name` parameter; teammates join the session's implicit team just by being spawned.
+ **Never inject Companion identity into teammates** — user-scoped `select_companion` race; only the
  Lead carries a voice. Fail loud on the env-flag, degrade gracefully on identity.
+ **The Lead owns ticket state** — "In Progress" at dispatch, "In Review" after the integration PR
  and ci-review pass, never "Done". Verify each move, retry once, soft-fail loud only on
  workflow/permission rejection.
+ **Lead reviews, never merges** — Deliver (merge, close ticket, move to Done) is the human's job.
+ **Always tear the team down** (`references/agent-teams.md` § Full teardown) — even on failure paths.

## References

+ `${CLAUDE_PLUGIN_ROOT}/references/integration-pipeline.md` — everything after implementation: simplify, AC+DoD, verification, gates, docs, PR, CI
+ `references/worker-dispatch.md` — worker contract, three backends, AC-review rule, bug-hunt dispatch, integration-branch/single-CI
+ `references/codex-dispatch.md` — Codex single-detach rule + chunk-brief template
+ `we/scripts/worker-launch.sh` — foreign-engine launcher (reads `.weside/engines.local.json`)
+ `references/mode-b-lessons.md` — hard-won Mode B field lessons (mandatory read before chunk dispatch)
+ `references/rehearsal.md` — `--rehearsal` procedure
+ `references/fixture-story.md` + `references/fixture-refinable-story.md` — rehearsal fixtures
+ `${CLAUDE_PLUGIN_ROOT}/references/programme-discipline.md` — multi-wave programmes: the state file, decision latency, the `/loop` shape
+ `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md` — env-flag prerequisite + full teardown
+ `we/skills/council/SKILL.md` — the Agent-Teams machinery this skill mirrors
+ `we/skills/develop/SKILL.md` — the dev-only worker skill
+ `we/skills/refine/SKILL.md` — the Write-only refiner skill
+ `scripts/orchestration.py` — `story state|status|checkpoint` (the state model + tracking)
+ `scripts/test_epic_state.py` — unit tests for `compute_epic_state` and the git evidence
