---
type: story-plan
story: worker-launch-backend
depends_on: []
comments_read_through: none
created: 2026-10-31
status: approved
parallel_groups: []
---

# Plan: Configurable worker launch backend (subagent or own process)

## Context

`/we:orchestrate`, the refine lanes of `/we:orchestrate` and `/we:story`, and
`references/worker-dispatch.md` § Choosing the worker dispatch every dev worker
as an `Agent` subagent (`worker-dispatch.md:18`, `orchestrate/SKILL.md:14` and
`:84`, `story/SKILL.md:67`, `AUTHORING.md:35`). A subagent bills the account of
the session that calls it. A setup that pins its Lead session to one account
(for example a session that carries Remote Control) and lets worker processes
run on a rotating login therefore burns exactly the account it wants to spare.
Such setups already run workers as their own background sessions
(`claude --bg -n <name> …`, started through a site-specific launcher), steered
by `SendMessage`, with the end signalled by `notify_when_idle`;
`references/companion-session.md:52` already knows `claude --bg` workers. This
story makes the launch backend a repo setting: `agents.worker_launch` in
`.weside/config.json` is either `"subagent"` (the default, today's behaviour,
unchanged) or a command template with placeholders. Every step of a worker's
life — dispatch, brief, steer, report, watchdog, finish, stop — works with both
backends. The plugin stays site-neutral: it names no launcher, no account, no
person. The gate rule (a gate run without a verdict is never restarted
automatically, #121) holds unchanged for both backends. No ticket exists
(ticketing is GitHub Issues, slug only); this plan works from the dispatcher's
brief. Proper names of the owner in every file this story touches become
"owner" (`AGENTS.md` § Conventions: no internal names in `we/`).

## Acceptance Criteria

1. **Given** a repo whose `.weside/config.json` has no `agents.worker_launch`
   or sets it to `"subagent"` **When** the Lead dispatches an implementer,
   finisher or refiner **Then** it dispatches the same `Agent(...,
   isolation="worktree")` call as on `origin/main` today, and
   `python3 we/scripts/worker_launch.py backend` prints `subagent`.
2. **Given** `agents.worker_launch` is a template such as
   `"my-launcher {name} --bg --agent {agent} {brief}"` **When** the Lead runs
   `worker_launch.py launch --worktree <wt> --name <name> --agent we:dev-medium
   --brief-file <file>` **Then** the brief is copied to `<git-dir>/we-brief.md`,
   a marker `<git-dir>/we-worker.json` holds `name`, `lead`, `agent` and
   `launched_at`, the template runs without a shell with cwd `<wt>`, and
   `claude agents --json` lists a session with that `name` and that `cwd`.
3. **Given** a template with an unknown placeholder, without `{brief}`, or with
   a placeholder inside a larger token (`--x={name}`) **When** `launch` or
   `backend` runs **Then** it exits non-zero naming the offending placeholder
   and launches nothing.
4. **Given** the Lead session has no name in `claude agents --json` **When**
   `launch` runs **Then** it exits non-zero with "name this session first" and
   launches nothing.
5. **Given** a session whose worktree carries the marker **When** its turn ends
   without a `SendMessage` to the marker's `lead` in that turn **Then** the
   Stop hook `worker_report_gate.py` blocks once with the report instruction;
   with such a send, with `stop_hook_active`, or without a marker it passes.
6. **Given** a process worker that finished its chunk **When** it ends its
   turn **Then** the Lead receives the § Report fields as one cross-session
   message from the worker's name, and the idle notice its dispatch
   subscription (`notify_when_idle`) asked for.
7. **Given** a running process worker **When** the Lead runs `worker_launch.py
   stop --name <name>` **Then** `claude stop <id>` ends it, `claude agents
   --json` no longer lists it as running within 30 s, and the command exits 0;
   an unknown name exits non-zero.
8. **Given** a process worker whose session ended without a commit
   **When** `watch-worker.sh <wt> <name>` polls **Then** it exits 4 with
   `exited: <name>`; a subagent worktree (no marker) keeps exit codes 0–3.
9. **Given** a session whose worktree carries the marker **When** it runs
   `gh pr merge <PR> --auto` **Then** `automerge_gate.py` refuses it as it
   refuses a subagent today; `--disable-auto` still passes.
10. **Given** `skills/setup/SKILL.md` § 3 **When** `python3
    scripts/validate-consistency.py` runs **Then** it fails when a key read as
    `agents.<key>` under `we/hooks` or `we/scripts` is missing from the schema
    block, or when the placeholder set in `worker_launch.py` differs from the
    one `worker-dispatch.md` § Worker launch backend lists.
11. **Given** the files this story touches **When** `rg -n Foxy` runs over
    them **Then** it finds nothing.

## User Journey

1. The owner of a repo sets `agents.worker_launch` to their launcher template
   (or leaves it unset). 2. They run `/we:orchestrate <KEY>`. 3. The Lead
   refines, dispatches, steers, receives the report, stops the worker and opens
   the PR as before; with a template every worker is a background session of
   its own, visible in `claude agents`, billed to the login it starts on. The
   story is done when that run walks end to end with both backends.

## Testing Requirements

Repo default `tests-after` (no `test_discipline` set): tests in the same phase
as the code, run with `python3 -m pytest -q we scripts`.

- AC 1, 2, 3, 4, 7: `we/scripts/test_worker_launch.py` (new) — template parse
  and render, marker and brief file, refusal arms, `claude` replaced by a stub
  executable on `PATH` that records argv/cwd and answers `agents --json` and
  `stop`. Phase 1.
- AC 5: `we/hooks/test_worker_report_gate.py` (new) — transcript fixtures with
  and without a `SendMessage` to the lead, `stop_hook_active`, no marker.
  Phase 2.
- AC 8: extend `we/scripts/test_watch_worker.py` with a marker and a stub
  `claude agents --json` that no longer lists the name. Phase 2.
- AC 9: extend `we/hooks/test_automerge_gate.py` with a marker case and a
  `--disable-auto` case. Phase 2.
- AC 10: run `scripts/validate-consistency.py` red (drop the schema key, then
  a placeholder) and green; red arm first. Phase 1.
- AC 6: no unit test can show cross-session delivery; § Verification covers it.
- AC 11: `rg` in the Phase 3 gate.

## Verification

- **Oracle:** cli — the launch, report and stop arms are observable with
  `claude agents --json`, the Lead's received message and the process table.
- **Seed:** a scratch git repo with `.weside/config.json` →
  `{"agents": {"worker_launch": "claude --bg -n {name} --agent {agent} {brief}"}}`
  and a brief "send `branch: probe` to your Lead by SendMessage, then stop".
- **Asserted:** `worker_launch.py launch` exits 0; `claude agents --json` lists
  `name=probe-1`, `cwd=<wt>`; the Lead receives one cross-session message from
  `probe-1` starting `branch:`; the idle notice arrives; `worker_launch.py stop
  --name probe-1` exits 0 and the session is gone from the running list.
- **Not proven:** a launcher that rotates accounts bills the worker elsewhere —
  site-specific, owed by the owner on their setup; a worker started in a
  different permission mode than the Lead may hold the Lead's steers for
  approval (Claude Code's `SendMessage` contract) — the doc names it, the
  receipt records which mode the probe ran in.
- **Exit criterion:** the four Asserted lines reproduce on a second run; the
  `subagent` default produces the same dispatch text as `origin/main` (diff of
  the dispatch lines in `worker-dispatch.md` § Choosing the worker shows only
  added text).
- **Missing CLI verb:** none — `worker_launch.py` (Phase 1) is the verb.

## Technical Approach

Grep-derived, no code graph (the plugin repo has no graphify graph; `rg` over
`we/` and `scripts/`). Facts read on `origin/main` 88a4e40 and from the
installed Claude Code CLI: `claude --bg` prints an id that `claude stop <id>`
takes; `claude agents --json` lists interactive and background sessions with
`id`, `name`, `sessionId`, `cwd`, `pid`, `status`; `claude --agent <name>`
runs a session as that agent (effort and model from the agent file);
`SendMessage` addresses a local session by its name, and a sender running as
a subagent sends under its parent's address.

New names this plan builds (new): `agents.worker_launch`,
`we/scripts/worker_launch.py`, `worker_report_gate.py`, the marker field
`launched_at`, the timing events `WorkerLaunch` and `WorkerStop`.
`.weside/dor.md` and `.claude/worktrees/` are named as absent or rejected,
not built.

**One seam, one script.** `we/scripts/worker_launch.py` (new, importable,
CLI) owns everything that differs between the backends, so the skills name a
command, not a mechanism:

- `backend` — reads `.weside/config.json` → `agents.worker_launch`; prints
  `subagent` or validates and prints the template. Missing file or key →
  `subagent`.
- `launch --worktree <wt> --name <n> --agent <we:dev-…> --brief-file <f>` —
  resolves the Lead's address (the row of `claude agents --json` whose
  `sessionId` is `$CLAUDE_CODE_SESSION_ID`; no row or no name → refuse, AC 4),
  copies the brief to `<git-dir>/we-brief.md` (`git rev-parse
  --absolute-git-dir` in `<wt>`: per-worktree, untracked, removed with the
  worktree), writes the marker, renders the template and runs it with
  `subprocess.run(argv, cwd=wt)`, no shell. Appends a `WorkerLaunch` line to
  `~/.claude/we-timing/<session>.jsonl` in `subagent_timing.py`'s shape, so
  timing compares both backends.
- `stop --name <n>` — resolves the id by name (and the marker's cwd when two
  rows share the name), runs `claude stop <id>`, polls `claude agents --json`
  until the row is gone or not running (30 s cap), appends `WorkerStop`.

**Template grammar.** `shlex.split(template)`; a token that is exactly
`{name}`, `{agent}` or `{brief}` is replaced by the value as one argv element;
any other `{…}` in a token refuses (AC 3). `{brief}` is the one-line prompt
`Read <git-dir>/we-brief.md and follow it.` — the brief never travels as a
shell-quoted argument and a reader can see what the worker got. `{name}` and
`{brief}` are required; `{agent}` optional (a launcher may fix the agent).

**Lead address and report.** The brief gets a line `Lead: <address>`; the
worker's report is one `SendMessage(to=<address>)` with the § Report fields,
then the turn ends. Subagent workers keep the final-message report.

**Hooks.** A process worker fires no `SubagentStop`, so the prompt hook on
`^we:dev-(medium|high)$` never sees it. A new command Stop hook
`worker_report_gate.py` reads the marker from the session's cwd (no marker →
exit 0 at once, cost for every other session is one `git rev-parse`), scans
the transcript of the current turn for a `SendMessage` tool_use whose `to` is
the marker's `lead`, and blocks once (`stop_hook_active` → pass) with the same
block text as the prompt hook. Deterministic instead of an LLM judgement: a
Stop prompt hook would run on every session's every stop. `automerge_gate.py`
gains the marker as a second worker signal next to `agent_id`
(`automerge_gate.py:218`). `watch-worker.sh` gains exit 4: marker present and
the name no longer running in `claude agents --json`.

**Error arms on the changed path.** `launch`: template invalid → exit 2, no
side effects; brief copy or marker write fails → exit 1 before the launch;
the launcher exits non-zero → exit 1 with its stderr, marker and brief file
removed (no half-launched worker the watchdog would watch). `claude agents
--json` fails or prints no JSON → exit 1 naming it, no `except Exception`.
`stop`: `claude stop` non-zero → exit 1 with its stderr; poll timeout → exit 3
"still running". The Stop hook catches only `OSError`/`json.JSONDecodeError`
on marker and transcript reads and then passes (a hook must never wedge a
session).

**Writes into two systems.** `launch` writes files then starts a process:
files ok + launch fails → files removed (above); launch ok + timing append
fails → ignored (measurement only, as `subagent_timing.py` does). `stop` has
one write (`claude stop`).

**Who reads the backend.** Every `we:dev-*` dispatch in the touched files:
implementer and parallel chunks (`orchestrate/SKILL.md:97-143`), finisher
(`:143`), the ci-review dev-medium with `cwd=<wt>` (`:170-171`), the refine
lane (`:84`), `/we:story` step 3 (`story/SKILL.md:67`). `we:explore-medium`
readers and council lenses stay subagents: read-only and short, and the
brief's goal names implementers.

**Process-backend worktree.** The Lead creates it itself, because
`isolation: "worktree"` is an `Agent` parameter:
`git worktree add <repo>-<KEY>[-p<N>] -b <type>/<KEY>-<slug> origin/<default>`
(the same sibling naming as the integration worktree, `orchestrate/SKILL.md:137`);
the branch carries its final name, so the rename step applies only to the
subagent backend. The bootstrap step is unchanged. A finisher or ci-review
worker in an existing tree launches with `--worktree <that tree>`.

**Steer, watch, stop with the process backend.** Steer: `SendMessage(to=<name>)`
as today; right after `launch` the Lead sends one `SendMessage(to=<name>,
notify_when_idle=true)` without a message (pure subscription) and renews it
after each steer. Watchdog: `watch-worker.sh` unchanged in arming and
`TaskStop`-by-task-id of the watchdog itself. Stop: `worker_launch.py stop`
instead of `TaskStop`, then remove the worktree as today.

## Implementation Phases

### Phase 1: Launcher script, config schema, consistency check

- **Goal:** `worker_launch.py backend|launch|stop` works and is tested; the
  setup schema names `agents.worker_launch`; the validator keeps schema,
  readers and placeholder list in step.
- **Files:**
  - `we/scripts/worker_launch.py` (new)
  - `we/scripts/test_worker_launch.py` (new)
  - `we/skills/setup/SKILL.md` (§ 3 schema block: `"agents": {
    "visible_teammates": false, "worker_launch": "subagent" }`, one line on
    the template)
  - `scripts/validate-consistency.py` (new check: `agents.<key>` readers vs
    schema; placeholder set vs `worker-dispatch.md`)
- **Risk:** ordinary — a new script; the promise "the `subagent` default
  changes nothing" holds because no skill reads the script until Phase 3.
- **Approach:** stdlib only (`json`, `shlex`, `subprocess`, `pathlib`).
  `PLACEHOLDERS = ("name", "agent", "brief")` as the one home the validator
  reads by import or regex. The placeholder check in the validator matches the
  list against the backticked placeholders in `worker-dispatch.md` § Worker
  launch backend, which Phase 3 writes; until then the check skips a missing
  section with a message, and Phase 3 makes it binding (red arm then).

### Phase 2: Hooks for process workers

- **Goal:** a process worker is held to its report, refused a merge, and
  noticed by the watchdog when it dies.
- **Files:**
  - `we/hooks/worker_report_gate.py` (new)
  - `we/hooks/test_worker_report_gate.py` (new)
  - `we/hooks/hooks.json` (Stop entry, command hook, after `question_gate.py`)
  - `we/hooks/automerge_gate.py` (marker as worker signal, docstring)
  - `we/hooks/test_automerge_gate.py`
  - `we/scripts/watch-worker.sh` (exit 4, header line)
  - `we/scripts/test_watch_worker.py`
- **Risk:** ordinary — but one promise across paths: "a worker never merges"
  must hold for both backends (`agent_id` and marker); the marker read must
  never block a non-worker session (missing `git`, no repo, unreadable file →
  pass).
- **Approach:** one helper reading the marker (`git rev-parse
  --absolute-git-dir` from the payload's `cwd`), shared by both hooks by
  import from `worker_launch.py` (`sys.path.insert` to `we/scripts`, as
  `materialize_on_start.py:36` does). Transcript
  scan as `conflict_gate.py:_scan_transcript` does it: the entries after the
  last user or cross-session message.

### Phase 3: Instructions for both backends, owner wording, version

- **Goal:** the four skills and the dispatch reference describe dispatch,
  brief, steer, report, watchdog, finish and stop per backend; no proper name
  of the owner remains in the touched files.
- **Files:**
  - `we/references/worker-dispatch.md` (new § Worker launch backend: config,
    placeholders, worktree, Lead line, report by `SendMessage`, idle
    subscription, stop, permission-mode note; § Choosing the worker points at
    it; § Report says how each backend delivers; § Watchdog exit 4; "Foxy" ×3
    → owner)
  - `we/skills/orchestrate/SKILL.md` (intro, refine lane, Build, brief block
    `Lead:` and `Report:` lines, While a worker runs, finisher, ci-review
    worker, Close the run stop; "Foxy" ×8 → owner; stays near its current
    length, mechanism lives in the reference)
  - `we/skills/develop/SKILL.md` (§ 2 process worktree: branch already named;
    § 6 report by `SendMessage` to the brief's `Lead:` when the brief has one)
  - `we/skills/story/SKILL.md` (step 3 refiner dispatch per backend; "Foxy" ×2
    → owner)
  - `we/skills/refine/SKILL.md` (step 5: a brief with a `Lead:` line → report
    as one `SendMessage`; "Foxy" ×2 → owner)
  - `we/AUTHORING.md` (Built-ins row "Worker isolation" names both backends)
  - `AGENTS.md` (layout: `worker_launch.py`, Stop report gate)
  - `docs/workflow.md` (dispatch diagram node `:30` and the paragraph at
    `:97-100`: one sentence on the setting)
  - `we/.claude-plugin/plugin.json` (version 7.32.0, or the next minor on the
    base at build time)
- **Risk:** ordinary — instruction budget (`check-instruction-budget.py`) and
  `orchestrate/SKILL.md` already over 150 lines with its reason line; keep the
  mechanism in the reference and the skill to one pointer per step.
- **Approach:** the brief block in `orchestrate/SKILL.md` gains
  `[Lead: <address> — report by one SendMessage to it (process backend)]`; the
  report line keeps "final message" for the subagent backend. `TaskStop` lines
  become "stop the worker (`worker-dispatch.md` § Worker launch backend)".
  The gate-rule paragraph (`worker-dispatch.md:79-83`, `develop/SKILL.md:64-66`)
  stays word for word.

## Out of scope

- Orchestrator reference and question IDs — own follow-up story (brief).
- `/we:handoff --park` — follow-up (brief).
- Saga status `parked` — follow-up (brief).
- Owner-label prefix — follow-up (brief).
- Budget gate over `.weside/*.md` — follow-up (brief).
- Setting `agents.worker_launch` in any consuming repo's own
  `.weside/config.json` — that repo's change, not the plugin's.
- `/we:retro` auto mode and `/we:ci-review` dispatches outside
  `/we:orchestrate` — they dispatch no implementer today; follow-up if a run
  shows them billing the Lead's account.

## Constraints and Pins

**Constraints:** plugin stays site-neutral (`AGENTS.md` § Conventions: no
internal names, paths or accounts in `we/`); one home per fact
(`AUTHORING.md`); hooks are deterministic Python, stdlib only; skills under
150 lines or a reason line.
**Pins:** the `subagent` backend's dispatch shape, brief block and report
path stay as on `origin/main` 88a4e40; `teammate_gate.py` behaviour
unchanged; the gate rule ("a gate run that ended without a verdict is never
restarted automatically", `worker-dispatch.md:79-83`, `develop/SKILL.md:64-66`)
unchanged in wording and effect; `watch-worker.sh` exit codes 0–3 unchanged;
the `SubagentStop` prompt hook unchanged.
**DoR:** the repo has no `.weside/dor.md`; the plan-format refined scan applies.

## Design Decisions

| Decision | Alternatives considered | Why this, decided by whom |
|---|---|---|
| Config key `agents.worker_launch`, `"subagent"` default or a template | a userConfig option in `plugin.json`; a separate `workers` block | the brief names it; `agents.visible_teammates` already lives there — dispatcher brief |
| One script `worker_launch.py` renders and runs the template, no shell | the Lead runs the rendered template in Bash | quoting and validation in one tested place; skills name a verb — refiner |
| Brief travels as a file in the worktree's git dir, `{brief}` is a one-line pointer | the whole brief as one argv element | no quoting, no length or newline issues, a reader sees what the worker got — refiner |
| Lead address from `claude agents --json` by `$CLAUDE_CODE_SESSION_ID`, refuse when unnamed | reply to the `from` of a first steer | deterministic and checkable before launch — refiner |
| Marker in `<git-dir>/we-worker.json` as the worker signal for hooks | an environment variable set at launch | a launcher may clear the environment; the git dir dies with the worktree — refiner |
| Deterministic Stop hook for the process report | a Stop prompt hook | a Stop prompt hook runs on every stop of every session; the marker scopes the command hook — refiner |
| Only `we:dev-*` dispatches follow the backend; explorers and council lenses stay subagents | everything through the backend | read-only and short; the brief targets implementers — refiner |
| Process worktree created by the Lead, sibling `<repo>-<KEY>[-p<N>]`, branch named at creation | a worktree under `.claude/worktrees/` | matches the integration worktree convention; no rename step — refiner |

## Code Guidance

**DO:** keep every backend difference behind `worker_launch.py` and § Worker
launch backend; test the script against a stub `claude` on `PATH`; return
early in the Stop hook when no marker exists. · **DON'T:** name a site's
launcher, account or person in `we/`; pass the brief through a shell; change
the subagent path's text beyond added pointers; restart a gate run that ended
without a verdict.

## Security Review Required

No — no money, auth, tenant isolation or migration. The template runs as
argv without a shell and comes from the repo's own config, which already
controls the worker's commands.

## Documentation Impact

- **Docstrings** — `worker_launch.py` (grammar, marker, exit codes),
  `worker_report_gate.py` (why deterministic), `watch-worker.sh` header (exit 4).
- **Architecture doc** — `worker-dispatch.md` § Worker launch backend is the
  one home.
- **ADR** — none; the default keeps behaviour and the switch is one key.
- **Generated** — none.
- **New doc** — none.
