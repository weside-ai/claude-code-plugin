---
name: orchestrate
description: >
  The Lead: reads state from git, refines what has no plan, dispatches workers for what does,
  integrates, runs CI once on one PR. Triggers: "/we:orchestrate", "orchestrate the epic",
  "dispatch the ready stories", "run the phases".
---

# /we:orchestrate

The Lead — the session running this skill — boots knowing where the work stands, decides what
each story needs next, dispatches it, integrates what comes back, and reviews the combined diff.
CI runs **once per repo the wave touches** — one PR for the story, plus one in a repo that had
to ship a verb for it. The Lead never merges; Deliver stays human.

**Cost model:** refiners run on Opus (the plan is the artifact every later worker follows), dev
workers on cheap-tier Claude, Codex, or a foreign engine; the Lead plans, integrates, reviews.
N workers = N dev costs + one CI. A story too small for a worker runs `--solo`.

**One pipeline, three dispatch shapes.** Every run ends the same way — implement → simplify →
AC/DoD gate → verification → gates → docs → PR → one CI pass — owned by
`${CLAUDE_PLUGIN_ROOT}/references/integration-pipeline.md`. What differs is who implements:
workers per Story, workers per phase (Mode B), or nobody (`--solo`).

**Forward momentum, gated.** The Lead's default state is working toward the merge: while CI or a
worker runs, fill the refine lane or prepare the next briefs, and say what you are doing —
"waiting for CI" is never the whole answer. Non-gate work goes behind the merge. Intermediate
states go to the state file, not the chat; the human hears from the Lead at wave boundaries, at
the Decision Queue, and at a gate — where you stop fully and ask one crisp question with a
recommendation. Two questions have a fixed shape:

- **`status`** — three parts, ≤ 5 sentences: what stands (one line per open item), what the
  human must do (usually nothing), what the Lead does next.
- **"is it still running?"** — evidence first (the Step-7 ladder: `ListAgents`, the worktree's
  `git status`/`log`, the report file, the rollout file), then what you cannot tell, then the one
  probe you are running now. Never answer a liveness question with a status roll-up.

## Prerequisites

```
Read("${CLAUDE_PLUGIN_ROOT}/references/verification.md")
Read("${CLAUDE_PLUGIN_ROOT}/references/long-running.md")
Read(".weside/orchestrate.md")
```

`.weside/orchestrate.md` is the repo's own dispatch notes — worktree bootstrap, generated
artifacts, gate baselines, single-owner host resources, risk-class file lists, where plan and
state commits may land. Absent → derive the same items from the repo's `CLAUDE.md` and
always-loaded rules, say in the roll-up that the file is missing, and offer to write it.

Agent Teams must be enabled — flag, abort text and teardown: `references/agent-teams.md`. The
session must be on `acceptEdits` or bypass (or carry a Bash allowlist): under the default mode a
teammate's Bash is denied and a dev worker dies on its first command. Refiners write a file and
run nothing, so they are unaffected; `--solo` dispatches nothing.

## Invocation

```
/we:orchestrate <epic>                      # state + next actions; dispatch on confirm
/we:orchestrate <story-key>                 # single Story: its phases as work-chunks (Mode B)
/we:orchestrate <key> <key> …               # ad-hoc roster: N stories, no epic
/we:orchestrate <story-key> --solo          # single Story, no workers
/we:orchestrate                             # most recently active epic, then status
```

Free text after the keys is an instruction to the Lead ("… mit codex", "… 3021 erst refinen") —
honour it, and when a Step-3 signal or a risk class contradicts it, that is one Decision-Queue
question, never a silent override. A backend named in the invocation is a standing pick for the
run: the per-chunk confirm shows it pre-selected instead of asking again.

**Step 0 — resolve the target.** **Single Story** when one key is given and it matches
`docs/plans/{KEY}-story.md` (or its ticket resolves to one) → Mode B over that plan's
`### Phase` blocks, whatever its `epic:` says — a single key is a single Story. **Ad-hoc roster** when several
keys are given without an epic → the Epic path over exactly those stories, with the state
derived by hand (Step 2); the **first key** in the invocation is `<primary-key>` everywhere
below. `--solo` forces the single-Story shape without dispatch. Otherwise an **Epic** (slug or
ticket key) → Steps 1–10.

## Workflow

### Step 1: Boot from state

**State file:** `docs/plans/<epic>-state.md` for an epic, `docs/plans/<primary-key>-state.md`
for a single Story or an ad-hoc roster. It is the first thing read and the last thing written in
every run: decisions taken, what was tried, per dispatch the worker name, backend, branch,
worktree and the chunk's gate list (what a rescue re-runs after a compact). Missing → write it after the state read and before the first dispatch
(`references/programme-discipline.md`); where it is committed is a repo fact
(`.weside/orchestrate.md`).

Then, from living files only: the Epic plan (`## Success Criteria` is the lens for done; no epic
file → synthesise the frame from the stories), every story's plan **completely**, every ticket
**with comments** (newest wins, name conflicts — `references/ticketing.md`; a comment that asks
for a check is work: answer it by reading the repo now, before the confirm), a recent
`docs/handoffs/` entry, the state (Step 2). The `refined` checkpoint means the plan passes
`references/dor-scan.md` — the same three checks the CLI computes — **and carries no
`## Open Fork` section** (a refiner that stopped at a fork writes one; the scan cannot see it):
write it now, whoever wrote the plan; a plan with an open fork is `draft` and its fork is a
Decision-Queue item. When the Lead answers a fork by rewriting the plan, it deletes the
`## Open Fork` section — no worker builds past one. `quality/dor.md` plus `<repo>/.weside/dor.md` are the Lead's approval read at the
confirm: a plan that fails a row there goes back to the refine lane with the row named, however
the CLI classified it. An investigation that retires a phase rewrites the plan before the confirm
— the Done check (Step 10) reads the rewritten plan, and a plan the Lead rewrote is presented at
the confirm gate like a refiner's, with the evidence that retired the phase.

Render "where we stand" — the state-file path in its first line, so a resumed Lead reads it
instead of guessing it — and **wait**: no dispatch without an explicit go. The confirm gate
presents: the stand, the wave map (which story/phase runs when, on what), the disjointness
result, each chunk's risk class, the executor per chunk, the verbs a verification will need in
another repo, and the Decision-Queue batch — one message. Steps 5.1–5.5 are computed read-only
to fill it; 5.6–5.8 mutate and run after the go.

### Step 2: Read the state

For an epic:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story state <epic> \
  --plans-dir docs/plans --in-flight "{keys you dispatched this session}" \
  [--base <ref>] [--integration-branch <branch>] [--refine-cap N] [--develop-cap N]
```

First matching rule wins — the order is load-bearing:

| State | Evidence | Next action |
|---|---|---|
| `shipped` | ticket in review/done/merged, or a `pr_created`/`ci_passed` checkpoint | — |
| `integrated` | story branch is an ancestor of the integration branch | wait for the wave |
| `built` | a story branch has commits beyond the base | **INTEGRATE** (Lead, serial) |
| `refined` | plan passes the DoR scan | **DEVELOP** (worker, ≤2) |
| `draft` | plan exists but fails the scan | **REFINE** (worker, ≤3) |
| `idea` | only a mirror row or a ticket | **REFINE** (worker, ≤3) |

Four limits of the CLI: it rosters from plan files and the epic's mirror table, so a story that
exists only as a ticket or in the epic's prose is **missing from its output** — reconcile the
roster against the epic plan and the ticketing tool's children before trusting it, and refresh
the epic's mirror block (`/we:epic`) with what you found so the next wave does not repeat it; it returns an
empty roster (`epic_resolved: false`) when the key is not an epic; it cannot see what you
dispatched (`--in-flight`); and it cannot carry a Step-3 signal — a `refined` story the comments
have overtaken still prints `DEVELOP`, and the Lead overrides that by hand, every wave. `story
status` on a key it has never seen answers `not_started` with no checkpoints — not an error.
For a single Story or an ad-hoc roster the evidence is the plan file, `story status {KEY}`, `git branch --list 'feat/{KEY}-*'`, `git worktree list` and origin — the same
ladder by hand. **On a resumed run** a branch or worktree for a key is in-flight until proven
otherwise.

A `built` branch nobody in this session dispatched (no worktree, no checkpoint) is adopted only
after the human confirms it is abandoned, and only after you verified that its commits cover the
plan's `**Files:**`; adoption moves the ticket to In Progress like a dispatch would, and the branch is merged onto
the integration branch as it stands before it is integrated — it was cut from whatever `main`
was then. Git is asked first because it cannot forget;
a story that shipped without a plan comes back `built-without-plan` — name it, the gate then has
no ACs.

### Step 3: The five human signals

A refiner writes a plan from front-loaded context; it cannot make a decision that was never made.
Check every story that is about to enter a lane — `draft`/`idea` before refine, and `refined`
before develop for signal 5, because a plan the comments have overtaken is exactly a refined
story. Any one fires → Decision Queue, with your recommendation attached:

1. an open question in the ticket (summary, description, or an unanswered comment);
2. the epic plan names it and nothing more;
3. a caveat in the mirror notes (`TBD`, `open`, `unclear`, `needs decision`, `blocked on`);
4. it freezes an interface others consume — recommendation: first and serial; find the
   dependents by asking the seam's callers (the repo's code graph or `rg`), put the residue to
   the human, and write `depends_on: [KEY]` into the dependents' plan frontmatter so the CLI
   holds them (in Mode B the wave map and the state file carry the order instead);
5. comments contradict the description or the plan (newest wins; a scope change is a decision;
   a refined story with this signal goes back to the refine lane, not to a worker; the plan is
   what the CLI reads, so the re-refine rewrites it, and the state file records why).

None fires → dispatch a refiner, and pass what you checked as the brief's context block.

### Step 4: The Decision Queue

Everything that needs the human — Step-3 questions, forks a worker reported, whether to cut an
RC, a risk-class executor call, **and finished plans waiting for approval** — goes to them **as
one batch at a wave boundary**, not per item. The unit is a decision, not a story; the moment
before the first dispatch is a boundary; when a batch outgrows the readable size (two to four
plans, a handful of decisions), split it into two batches — never into per-item interrupts.
Plans are approved before their build starts: a wrong plan produces correctly built wrong code.

Every open item is written to the state file's *Open decisions* section the moment it is asked and
re-presented on the first roll-up after a resume; a resume word ("weiter", "go on") answers the
run, never an open decision. A story the human has nothing to say about yet is **parked**: it
leaves every lane and its ticket goes to the repo's backlog state (`.weside/orchestrate.md`).

### Step 5: Preflight

1. **Caps:** refine ≤ 3, develop ≤ 2, integrate serial. Raise the develop cap only for
   demonstrably disjoint work, and say why.
2. **Risk class per chunk.** Money, auth, tenant isolation, a migration on such a table — the
   repo's file lists live in `.weside/orchestrate.md`, and the class follows the **call site**,
   not the file: a chunk that adds a call into a listed module is that module's class. A critical
   chunk is never on a cheap model tier (Sonnet/Haiku — "cheap-tier" is a model tier, not a
   backend): Opus, Codex with a complete brief, or the Lead itself; never fast-gates-only (the
   brief names the integration suite and the database); on a detached backend only when every constraint is verifiable at merge time and the checks are
   written down before dispatch, and a migration never on one at all (no channel for a wrong
   revision); and it gets
   full-surface AC review plus the bug-hunt over the integrated diff. A chunk too small or too
   critical for any worker is a **Lead-owned chunk**: its own worktree and `feat/{KEY}-lead`
   branch off the integration branch, the same gates, the same Step 8 A merge.
3. **Disjointness is about files, not topics.** Union each plan's per-phase `**Files:**` lists
   and intersect; non-empty → hold until the conflicting build lands. Pair a frontend story with
   backend slices, not with another frontend story. When ONE genuinely shared *resource file* (an
   i18n bundle, a barrel export, a route manifest) is the only overlap, do not serialize: give
   each worker disjoint top-level sections of it in the brief, declare the catch-all section
   (`common`, `shared`) read-only for everyone, and verify at merge that every hunk
   (`git diff | grep '^@@'`) falls inside its worker's range. A shared **component or function**
   is a shared seam, not a shared bundle — it serializes. A seam across different files is
   invisible to the intersection; the epic plan's Sequencing and `depends_on` carry it.
4. **`parallel_groups` semantics:** phases absent from every group run serially in plan order;
   a group runs after every lower-numbered phase has merged; inside a group ≤ 2 concurrent.
5. **Lead voice (optional):** with `mcp__plugin_we_weside-mcp__get_council`, adopt the Lead's
   review-role Companion for Step 8. Teammates never get an identity.
6. **Integration branch + worktree, now.** Worktree
   `$(git rev-parse --show-toplevel)-<epic-or-key>-integration` on
   `feat/<epic-or-key>-integration`; every integration command via `git -C`. Reuse an existing
   worktree only when it is on **this run's** branch — a path on a foreign branch is another
   run's, never reset, never adopted. The main worktree stays on the default branch. The
   integration worktree has exactly one writer: handing a PR to a second engine hands over the
   work — review read-only until its work is a commit on the remote. Run the repo's worktree
   bootstrap **and its install rule** here, once (`.weside/orchestrate.md`); until the install
   has run, per-merge broad checks are backend-only.
7. **Chunk worktrees are the Lead's.** For every chunk, whatever the backend, **when its wave
   starts** — off the integration branch as it stands then, so a later chunk carries the merged
   foundation: `git worktree add <path> -b <branch> <integration-branch>` + the repo bootstrap.
   `story checkpoint {KEY} git_prepared` once per story, at its first worktree (checkpoints
   append; a second row regresses the recorded phase). `EnterWorktree` cannot take a base ref,
   so a worker that creates its own worktree branches off the default branch and silently loses
   the wave's merged foundation.
8. **Verbs the verification will need.** Read each plan's `## Verification`; a seed or assert
   the repo's CLI cannot do yet is a Lead-owned chunk in the repo that owns the CLI, cut in
   wave 0 so its PR's merge window overlaps the build — not discovered at Step 8 B when every
   worker is gone.

### Step 6: Dispatch the wave

**Before every dispatch:** `git pull` on the default branch and re-read the plan — another
session may have built it overnight — and `test -d "$PWD"` in a session worktree (subagents
inherit the path). Spawn every Agent teammate of a wave in **one** assistant message; a Codex
chunk is a Bash call and goes in the same message or the next, it does not matter. There is one
implicit team, no `team_name`, no task list — the state file is the durable dispatch record.
Workers run `/we:develop` and write no checkpoints; every checkpoint is the Lead's.

**Ticket state at dispatch:** a **develop** dispatch moves the story to In Progress (verify,
retry once, soft-fail loud). A **refine** dispatch does not — the plan's approval moves it to the
repo's plan-approved status (`.weside/orchestrate.md`), and a story refined but not built this
wave is not In Progress.

```python
Agent(name=f"refiner-{TICKET}", subagent_type="general-purpose", model="opus",
      description=f"Refine {TICKET}", prompt=<Refiner-Brief>)
Agent(name=f"worker-{TICKET}", subagent_type="general-purpose", model="sonnet",
      description=f"Build {TICKET}", prompt=<Worker-Brief>)
```

Chunk branches: `feat/{TICKET}-work` for a whole-story worker, `feat/{TICKET}-p{N}` for a Mode-B
chunk of phase N (or `p{N}-{M}` for a group), `feat/{TICKET}-lead` for a Lead-owned chunk. The
brief names the worktree path and branch the Lead created in Step 5.7; a Codex chunk gets it as
`--cwd`.

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

Refiners write into the main worktree; the Lead commits plans and state by explicit path there,
never `git add -A`, so a half-written plan is never swept into a commit. A refiner's only
liveness signal is the plan file (`ls -l docs/plans/{KEY}-story.md`). On the
report: run the DoR scan yourself (the body scan moves a story, not a claim) → passes → queue
the plan for the batch, `story checkpoint {KEY} refined`, commit → fails → re-dispatch **once**
with the missing item → still failing → Decision Queue.

#### Worker-Brief

```
You are worker-{TICKET}{-pN}, a teammate spawned into this session's implicit team. The lead is "team-lead".

REPO: {repo_root}. Start every bash command with `cd {repo_root}` and confirm
`git rev-parse --show-toplevel` before any git operation.
WORKTREE: `{worktree_path}`, already on branch `{branch}` (off `{integration_branch}`) and
bootstrapped. `cd` there; do not call EnterWorktree. Run: Skill(skill="develop") for {TICKET}
{--phases N}.

DEV-ONLY: implement {all phases | phase N}, committing per phase → fast local gates → AC-check
your diff (when `review.cross` is on; skip on a detached backend) → push {branch} → STOP. No `gh pr create`, no CI, no ticket transition, no doc pass — the Lead
merges every branch onto {integration_branch} and runs ONE CI on ONE PR.

FINISH FIRST: a small finding (≤ ~30 min) on the seam you touch gets FIXED in your branch —
"pre-existing" is no deferral reason. Product decisions, money-path changes and foreign-subsystem
redesigns go back to the Lead as QUESTIONS in your report; workers never create tickets. Surface a
design fork BEFORE you pin behaviour around it.

TESTS: {test_discipline from .weside/config.json; absent → tests-after: write tests in the same
change, after the code}. No implementation-coupled tests, no tautological assertions, mock at
system boundaries only.

FAST GATES: unit + fast smoke only. A test that needs a running database, queue or network
service belongs to the Lead's integration run — skip it and say so in your report. No
`yarn`/`npm install`, `jest`, `tsc` in a fresh worktree; report the skipped frontend validation.
{CRITICAL chunk (money / auth / tenant isolation / migration): run `{integration suite}` against
`{database}` before reporting done — this chunk is never fast-gates-only — and append the run's
last 20 lines to WORKER-REPORT.md so the claim is checkable.}

REPO CONSTRAINTS: {from .weside/orchestrate.md — generated artifacts to regenerate and commit,
gate baselines, shared-file sections assigned to you and the sections you must not touch}

REPORT FILE: write WORKER-REPORT.md in your worktree root before you stop — what you built,
skipped, could not settle. It is not part of the change: do not `git add` it.

REPORTING IS NOT OPTIONAL: your plain-text output is INVISIBLE to the lead. Send EXACTLY ONE message:
  SendMessage(to="team-lead", summary="worker-{TICKET} done|blocked",
              message="<branch | commits: N | gates: lint ✓ types ✓ tests ✓ | AC-check: clean|N findings |
                        skipped: … | blockers: none|reason>")
NEVER report done without a pushed branch. Stopping early: write the report file, send the message, stop.
```

Both briefs carry rules inline that references also own — a worker on a foreign engine has no
plugin context. When a rule changes, update the owner AND the brief.

#### Executor selection (per chunk, at the confirm)

Read `.weside/config.json` (`tools.codex`, `execution.default`; absent keys mean cheap Claude)
and `.weside/engines.local.json` (absent means no foreign engine).

| Backend | When | How |
|---|---|---|
| **Cheap Claude** | default, or `execution.default: claude-sonnet\|claude-haiku` | `Agent(model="sonnet", …)` with the brief above |
| **Codex** | `tools.codex: true` + confirmed (per chunk, standing from the invocation, or `execution.default: codex`) | `references/codex-dispatch.md` |
| **Foreign engine** | profile in `engines.local.json` | `we/scripts/worker-launch.sh --engine <name> --cwd <worktree> -- <brief>` (brief: `references/worker-dispatch.md`) |

Risk class overrides the pick (Step 5.2). **Only an Agent teammate can be steered mid-flight**;
a Codex or foreign worker is a detached process with no inbound channel and no liveness signal.
On those backends the brief is the whole instrument: front-load every constraint, turn what you
cannot send into a merge-time check you write down at dispatch, and reconcile the file list with
the prose before dispatch — generated artifacts, `WORKER-REPORT.md`, and the foreign test files a
new required field or a new collaborator inside an existing function pulls in (`rg` its callers
under `tests/`); `WORKER-REPORT.md` is listed as write-allowed and **not committed**. Three of
five phases once stopped on that contradiction alone. A gate-baseline
file (allowlist, ratchet, coverage snapshot) is re-verified with the gate at merge, never by
arithmetic. Prefer an Agent when the shape may change under the worker; Codex when the brief can
be complete.

### Step 7: Monitor

1. **Idle ≠ done.** A worker idles between turns; wait for its `SendMessage`, which can take many
   minutes of silence. A message you send lands only at the worker's next turn boundary.
2. **State is truth.** To know a worker's state — long idle, ambiguous report, after a compact,
   before any roll-up claim — read evidence, in order: `ListAgents` (is the teammate alive) →
   `git -C <worktree> status`/`log` (is work landing; for a refiner: `ls -l
   docs/plans/{KEY}-story.md`, its only artifact) → `WORKER-REPORT.md` in the worktree →
   for Codex the rollout file and CPU time (`references/codex-dispatch.md` § *Is it still
   working?* — process count and `/codex:status` both answer confidently and wrongly) → only
   then nudge, at most once. Never spawn a replacement while the original may be alive: two
   workers on one host corrupt each other — kill, verify, then spawn. The state file says which
   backend and name each dispatch had; after a compact it is the only place that does.
3. **Never wait on a commit alone.** A Codex chunk can finish and die uncommitted; a worker that
   stops to ask writes nothing. Arm the wait on the worktree going dirty AND a timeout; when it
   fires, read the worktree yourself. A rescued tree is un-gated by construction: run the chunk's
   full gate list and the AC-check the worker owed before you commit it (crediting the worker in
   the trailer).
4. **A wait condition may only watch state the worker changes.** Anchoring on a branch the Lead
   moves while integrating (`git log <integration>..HEAD`) goes permanently false after the
   merge; anchor on a fixed sha, a remote branch's existence, or a file only the worker writes.

Roll-up: `refining: {…} | building: {…} | to integrate: {…} | waiting: {…} | waiting on your
merge in <repo>: {…}`. Refill lanes on
events, re-reading the state on every pass. Terminate the wave when nothing is in flight and no
lane can be filled; "everything left conflicts with an in-flight build" is serialization, not
deadlock. A `depends_on` cycle drains to the same predicate — name it rather than wait.

### Step 8: Integrate + review + CI

**Merge first, PR second.** Never open the PR while a **develop** worker of this wave runs; the
refine lane may stay busy — its output is a plan, not code.

**A — per worker, as each reports done.** Verify the worktree actually changed (`git -C
<worktree> status`/`log`) — success with no commits is a lost dispatch; re-dispatch, never
integrate an empty tree. Read `WORKER-REPORT.md`, then merge inside the integration worktree:

```bash
git -C "$INT_WT" merge <branch> --no-ff -m "chore(<TICKET>): integrate <branch>"
git -C "$INT_WT" push origin feat/<epic-or-key>-integration
```

Conflicts resolve by the plan's Constraints and Pins; a non-trivial one goes to the user. A
blocked worker's blocker is surfaced, never merged half-done. After each merge run the broad
check on the merged tree (type-checker, the affected unit AND integration suites), not the
chunk's slice — a foundation chunk's contract change breaks a sibling file no worker's gate
covers. Glue fixes the Lead makes are small, separately named integration commits. Checkpoint
`implementation_complete` once per story, from the diff after its last chunk merged — not from a
report.

**B — once, after ALL develop workers merged.** Sync `origin/main` into the integration branch if
it drifted (merge, not rebase), then run `references/integration-pipeline.md` over the merged
diff: simplify → AC+DoD gate → verification → gates → docs → PR → one CI pass → tickets to In
Review. What an orchestrated run adds:

- the install-gated frontend gates the workers skipped run here, with the repo's install rule
  (`.weside/orchestrate.md`);
- verification covers the journeys *the wave* claims — one walkthrough across three stories
  beats three that stop at their own seam; the receipt is written once per landed story into its
  plan's `## Verification`, each with its own "not proven" line; before starting a server, check who owns the
  single-owner ports (a busy port is a question, not a kill), and stop what you started, by PID,
  as soon as verification ends — not at worktree removal;
- the verb chunk from Step 5.8 has its own PR in its repo; until the human merges it the wave
  is **waiting on your merge in `<repo>`** — a roll-up state, named as such, and the story PR
  waits behind it because its verification receipt cannot exist yet (a red CI there is that PR's
  `/we:ci-review`, not this wave's). The wave's Done counts every repo the wave touched;
- a migration chunk gets a real-database `alembic upgrade → downgrade → upgrade` by the Lead — a
  worker in a throwaway worktree can only defer it;
- the bug-hunt is writer-aware across the whole wave: every chunk Claude-written and Codex
  configured → `/codex:adversarial-review`; any chunk from Codex, a foreign engine, or a tree the
  Lead committed for a dead worker → Claude's native `/code-review` over the whole diff
  (`references/worker-dispatch.md` § Bug-hunt);
- **every** story that landed moves to In Review. Confirm with `story status` before claiming a
  story shipped.

CI red after the one pass → report and stop; the human decides on `/we:ci-review`.

### Step 9: Close the wave

Write the state file first — one row per action this wave, decisions taken, what is open. Then
the roll-up (shipped-to-review / integrated / waiting, with reasons) and, if stories are waiting,
the next invocation (`pr_created` unlocks them before the human merges). Tear down every teammate
(`references/agent-teams.md` § Full teardown), even on failure paths; a detached backend (Codex,
foreign engine) has no message channel and is torn down by PID against its worktree cwd. Remove the chunk worktrees;
**keep the integration worktree and branch until Step 10** — the open PR points at the branch,
and a CI-review fix needs the tree. Before removing any worktree, kill the processes it started
by PID (`ss -ltnp` on the repo's ports, `ls -l /proc/<pid>/cwd` — `(deleted)` is an orphan,
yours to clear; a live cwd belongs to another session — coordinate, never kill; never `pkill -f`).

### Step 10: Close-out — after the human says "merged"

The human's word after merge is the trigger; the Lead does the rest in one pass and reports one
line: remove the integration worktree and delete the integration and chunk branches (local and
remote) — a story still waiting on the roster builds from post-merge `main`, so nothing here is
lost to it; move the tickets **that landed** to **Done** (verify) — the DoD's "Done is the human's" is satisfied by
that word, not by a click; refresh the epic mirror / state file with the merged PR; update the
story plan to what was actually built if it still describes an intention — a story is Done only
when every `### Phase` block's `**Files:**` actually changed, in every repo the plan names; do the
release or deploy the human asked for, and nothing they did not. Then say what is next (the state
read on the remaining roster).

---

## `--solo` — one Story, nothing dispatched

A plain feature branch in a worktree, the phases run in this session, the same pipeline at the
end. Reach for it when dispatch buys nothing: a single straight-line phase, a config change, a
one-function fix. `/we:story` already recommended the shape; follow it.

1. **DoR** — ticket with comments, the plan and every file it names, the 3-item scan
   (`references/dor-scan.md`). Failing scan → stop, name the item; `/we:story {TICKET}` is the
   fix. A plan older than the code it plans is the other stop.
2. **Worktree + ticket** — `EnterWorktree(name="{type}/{TICKET}-…")`, the repo bootstrap, In
   Progress, checkpoint `git_prepared`.
3. **Implement** phases in order, commit per phase, checkpoint `implementation_complete`.
   `parallel_groups` in the frontmatter means you should have run Mode B — note it.
4. `references/integration-pipeline.md` for everything after.

Don't ask how to run it — by the time a plan exists and this was invoked, the decision to build
is made. Interrupt only for: the circuit breaker after three failures in one phase, the AC+DoD
gate, a gap in the plan that reading the code cannot close, anything destructive.

## Mode B — phase dispatch (one coherent change, many phases)

The path for a single-Story target; also reachable from an epic run when one story is a phased
coherent change (a refactor, a migration) where N full builds would pay the QS cost N times. The
story plan is the state file's twin: its close-out rewrite (Step 10) is where the run's decisions
live.

- The plan's `### Phase` blocks with `**Files:**` are the chunk plan, `parallel_groups` the wave
  map (Step 5.4). **Re-run the discriminating check before every wave:** can each chunk land
  touching only its own files, with zero edits to a shared file the others also need? If two
  chunks both fill the same scaffolding, that is another serial foundation chunk first. There is
  often more than one shared layer; the real parallelism appears late, in the per-unit wiring.
- Chunks are `Agent(name=…)` teammates, Codex tasks, or Lead-owned, each in the worktree the
  Lead created on its `feat/{TICKET}-p{N}` branch off the integration branch, running
  `/we:develop --phases N` with a brief scoped to one chunk; targeted tests only. A critical chunk (Step 5.2) starts at `opus` or the Lead;
  builders default to `sonnet` only where the risk class is ordinary, `opus` also for a chunk the
  Lead can name as hard (a contract freeze, a delicate teardown).
- **Characterization as contract.** The first chunk pins current behaviour (green on unmodified
  code); a property the refactor newly *introduces* is flagged, never pinned. Later chunks keep
  the pins unchanged — moving a behaviour's locus is an explicit, reviewed pin rewrite, noted in
  the commit; silently weakening one is the failure.
- **Green is the start of chunk review.** Judge a builder's fork decision against the AC, not the
  test status; an over-claimed net is worse than an honest gap. The Lead reviews each diff,
  integrates onto one branch (broad check after each merge, Step 8 A), re-confirms the worktree
  root before trusting a green, runs QS once at the end → one PR.

## Standalone fallback

No weside account / no MCP → generic review lens; workers never needed identity. The Agent-Teams
flag is required regardless.

## Rules

- Workers implement and stop; refiners write and stop; the Lead alone runs the scan, writes
  checkpoints, integrates, and runs the pipeline. A per-worker PR or CI voids the single-CI
  contract.
- The Lead spawns with `Agent(name=…)`, all of a wave in one message — never with `Skill()`;
  a teammate loads its own skill with `Skill()`, which is what the briefs say.
- The Lead owns ticket state: In Progress at develop dispatch, In Review after the PR, Done on the
  human's word after merge (Step 10).
- Every worker commit carries `Co-Authored-By: <Engine> <Model> <noreply@…>`; the Lead never
  re-signs a worker's commit.
- Always tear the team down.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/integration-pipeline.md` — everything after implementation
- `${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md` — worker contract, backends, AC-review rule, bug-hunt matrix, foreign-engine brief
- `${CLAUDE_PLUGIN_ROOT}/references/codex-dispatch.md` — Codex dispatch, liveness, chunk brief
- `${CLAUDE_PLUGIN_ROOT}/references/programme-discipline.md` — the state file and the `/loop` shape
- `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md` — env flag + teardown
- `we/skills/develop/SKILL.md`, `we/skills/refine/SKILL.md` — the worker skills
- `scripts/orchestration.py` — `story state|status|checkpoint`
