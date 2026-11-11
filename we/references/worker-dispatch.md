---
name: worker-dispatch
description: How the Lead picks and dispatches a dev worker, the dev-only worker contract, the finish sequence before the first push, and the report. Shared by /we:master and /we:develop.
---

# Worker dispatch

## Contents

Choosing the worker · Worker launch backend · Dev-only worker contract · Finish sequence · Card worker · Lead checks around a worker
(premise check, code graph in the brief, watchdog, lane merge) · Report.

The Lead (`/we:master`) dispatches; the worker (`/we:develop`) obeys the contract below. A
worker cannot rely on reading this file: the Lead's brief carries every rule the chunk needs.

## Choosing the worker

- Dispatch shape: § Worker launch backend. A repo with a crew starts every `we:dev-*` worker through
  the template `worker_launch.py backend` prints (the crew's `launch.worker`) as a session of its own; only a repo without a crew (or a crew's
  fallback, § Worker launch backend) uses `Agent(name=…, subagent_type="we:dev-medium" | "we:dev-high", isolation="worktree", description=…, prompt=<brief>)`.
  A `name` without `isolation` opens a teammate pane; off by default (owner, 30.10.2026), the hook
  `teammate_gate.py` refuses it unless `.weside/config.json` sets `agents.visible_teammates: true`.
  Never `general-purpose`: a subagent inherits the session effort, and only the agent file's
  `effort:` overrides it (red arm, 27.09.2026).
- Default `we:dev-medium`. `we:dev-high` for: a promise that must hold across several code paths
  ("always", "exactly once"); transactions, money or idempotency; auth or tenant isolation; a fix
  routing around a fragile path; the second attempt after a failed worker; plan-writing (owner
  27.09.2026). The Lead writes the reason as one line in `description`; no reason, no `dev-high`
  (01.10.2026: 9 of 121 dispatches named none). A clearly bounded single fix stays medium: the bench
  (n = 27) found no difference there, and high costs about a third more time and money.
- Implementation never runs on Sonnet (owner 27.09.2026). `model: "haiku"` or `"sonnet"` only for a
  chunk the Lead names mechanical (a rename, a generated file, a gate run).
- Codex is not a dispatch backend; it reviews advisory only (owner 30.09.2026).
- One implementer per phase group by default. Measured over 18 runs (16.10.2026): an integrate merge
  costs ~15–20 min; the real cost of parallel work is the loop after the push (main merges, a second
  migration head, regenerated artifacts), and stacked branches netted about zero. Disjoint stories
  on separate PRs paid off. Most run time is waiting on CI and the human, which more workers do not
  shorten. Run chunks in parallel when the plan's
  `parallel_groups` say so, or when their `**Files:**` lists do not intersect and the contract
  between them exists on the base branch. Contract first, then fan out: the chunk that lays down
  schema, API and types merges into the integration branch, and the disjoint chunks start with
  `Base: git merge <int>`. Migrations, lockfiles, generated artifacts (`openapi.json`, typed
  clients) and gate baselines always serialize.
- Timing: the plugin hook `hooks/subagent_timing.py` appends one line per `SubagentStart`/`SubagentStop` (`ts`, `event`, `agent_id`, `agent_type`, `cwd`) to `~/.claude/we-timing/<session_id>.jsonl`, the measurement for comparing orchestration approaches; the same file gets `InstructionsLoaded` and skill-run lines for `/we:retro` and `/we:instruction-audit`. A file older than 45 days is deleted (`scripts/state_prune.py`: the audit's 30-day span plus a margin).

### What `isolation: "worktree"` does (Claude Code 2.1.283)

- The worktree branches from `origin/<default-branch>` (setting `worktree.baseRef`, default
  `fresh`). Run `git fetch origin` before the dispatch, or the worker starts from a stale base.
- The branch is named `worktree-<name>` with `/` rewritten to `+`. The worker renames it to the
  branch the brief names before its first commit.
- `isolation` and `cwd` are mutually exclusive. A worker for an existing tree (the integration
  worktree) gets `cwd=<path>` instead.
- The result returns the worktree path and branch. A worktree without changes is removed.
- All worktrees share one `.git`: a worker's local branch is visible to the Lead without a push.
- The repo's `post-checkout` bootstrap may not have fired. The worker runs the bootstrap from
  `.weside/orchestrate.md` itself and checks it before the first gate.

## Worker launch backend

One template decides how every `we:dev-*` worker starts (implementer, finisher, refiner, a
ci-review worker): the crew's `launch.worker` in a repo with a crew, `.weside/config.json` →
`agents.worker_launch` in a repo without one (or while the crew sets none). Both set and different:
`worker_launch.py` warns once and the crew wins. `we:explore-medium` readers and council lenses
stay subagents. Who may start workers, how many and how they are named: L0 §Sessions and the
master role card. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/worker_launch.py backend` prints the
template in force; the master's boot check and `/we:accept` read it there.

- A repo with a crew: a command template (below), never `"subagent"` (L0 §Sessions: build only in
  workers; a subagent reads and reviews, never builds). The launcher does not refuse the `subagent`
  backend itself: the master checks the setting before the first dispatch and asks the coordinator
  for a template when it is unset. One opt-in exception, checked at boot: when the first word of the
  template `worker_launch.py backend` prints is not on the host's `PATH` (`command -v`; a
  colleague's machine without the launcher), a crew with `launch.subagent_fallback: true` lets the
  master start build workers with the full `Agent` call of § Choosing the worker, `isolation="worktree"`
  included, and say so once in its first status; default `false`: the master stops and names the
  missing launcher.
- `"subagent"` (the default when unset), only in a repo without a crew: the `Agent` call of
  § Choosing the worker. A subagent bills the account of the session that calls it.
- A command template: each worker is a session of its own, billed to the login the command starts
  it on. Placeholders, each a token of its own: `{name}` (required), `{brief}` (required; becomes
  `Read <git-dir>/we-brief.md and follow it.`), `{agent}` (the `we:dev-*` agent, as `--agent
  {agent}`, so its effort and model apply). Example: `"claude --bg -n {name} --agent {agent}
  {brief}"`. The command starts the worker in the Lead's permission mode, or Claude Code may hold
  the Lead's messages for approval. With `we-worker`, the crew's `launch.worker_mode: bypass` starts
  a `--bg` worker in bypass (`default`: no `--permission-mode`), a window worker keeps its default
  mode; `launch.allow_bypass: true` adds `--allow-dangerously-skip-permissions`, and in a repo
  without a crew `WE_WORKER_ALLOW_BYPASS=1` does (a crew's value always wins): in the background
  nobody answers a prompt, and the `permissions.deny`/`ask` rules and the plugin's guards still
  hold under bypass.

### Name and brief

`we-worker` and `worker_launch.py launch` refuse a start (exit 2, before any file or session) whose
name does not start with the story key (crew `naming.key`, `<KEY>-<chunk>`). They warn, and once the
check is enforced refuse, a brief that lacks one of four Markdown headings with a body: `Ziel`/`Goal`, `Ausgabe`/`Output`, `Werkzeuge und
Quellen`/`Tools and sources`, `Grenzen und wann stoppen`/`Limits and when to stop` (a heading counts
when its text starts with the name). The grammar, the refusal template and `worker_launch.py check`
are owned by `scripts/worker_launch.py` (its docstring). A `--resume` start checks the name only.
Every start and every denial of the worker rights brake is one line in `<state dir>/brakes.jsonl`
(`worker_rights.brake_log`): the count of false alarms and of passing briefs.

### Worker rights

Every `we-worker` start passes `--settings` (`worker_launch.py settings`: the repo's granted rights
as `permissions.allow`, the never-list as `permissions.deny`, `WE_ROLE` and `WE_STORY_KEY` as `env`).
The brake is the PreToolUse hook `hooks/worker_rights_gate.py`, which holds under `bypassPermissions`:
in a repo the crew's `worker_rights.repos` names, a worker on its own keyed branch runs `gh pr ready`,
`gh pr comment` on its own PR and the crew's `branch_rc` without asking; every worker is denied the
never-list (secrets, delete, `main`, guard bypasses). Rules and limits: `scripts/worker_rights.py`
(its docstring). A denial names the Lead; the worker reports it and the Lead acts. A brake against a
misguided worker, no boundary: a script file passes it.

With a template, the Lead:

1. Creates the worktree: `git fetch origin`, then `git worktree add <repo>-<KEY>[-p<N>] -b
   <type>/<KEY>-<slug> origin/<default>`; the branch carries its final name, no rename. A finisher
   or ci-review worker launches in the existing tree. `claude --bg` refuses an untrusted directory;
   a worktree of a trusted repo is trusted (measured 31.10.2026), a fresh scratch repo is not.
2. Writes the brief to a file and runs `worker_launch.py launch --worktree <wt> --name <name>
   --agent <we:dev-…> --brief-file <file>` (`--agent` is required when the template has `{agent}`). It puts `Lead: <this session's name>` as the brief's first line
   (an unnamed Lead is refused: `/rename <KEY>` first), writes the marker `we-worker.json` into the
   worktree's git dir and runs the command there.
3. Subscribes with `notify_when_idle: true` on its first message to the worker, again on each
   steer. A steer is `SendMessage(to=<name>)`, as for a subagent.
4. Arms the watchdog (§ Watchdog). Its exit 4 `exited: <name>` means the session ended: read the
   report, else `claude logs <name>`.
5. Stops the worker with `worker_launch.py stop --name <name> --worktree <wt>` instead of
   `TaskStop`, once its report is integrated or dropped, also after exit 4: it removes the marker
   and the brief, then the worktree can go or the Lead can work in it.

The plugin ships a launcher: `scripts/we-worker` (installed next to `wclaude` by
`scripts/install_launcher.py`; `we-worker --help`), with the verbs
`status|stop|logs|waiting|checkpoint|is-worker`; `worker_launch.py stop` uses its `stop` when the template
starts with it. `stop` and `checkpoint` touch workers only: a name that hits a master or companion
refuses (`stop` names `claude stop <id>`, or `kill <pid>` for a window session); a launcher marker
counts only for the session it names. `worker_launch.py stop` without `--worktree` refuses a name
that runs in several trees. **Checkpoint** (`we-worker checkpoint <name>`, or
`worker_launch.py checkpoint --name <name>`): on an idle or stopped worker only, refused while
`claude agents` shows it working, busy or blocked on a prompt (one writer per worktree); commits
its tracked changes and pushes them to `wip/<branch without its type prefix>`; a new file, staged or
not, is named and never committed. Where a launcher brings
such verbs, the Lead steers and inspects through them instead of calling `claude logs` or `claude stop` itself; whether a worker still lives comes only
from `claude agents --json`, never from a log or a quiet tail.

The hooks treat a session as the worker only when the marker names its session id, so the Lead
working in the worker's tree is never one.

The worker reports by one `SendMessage` to its `Lead:`; its plain text never reaches the Lead. The
Stop hook `worker_report_gate.py` blocks a turn without that message, and `automerge_gate.py`
refuses its merge as for a subagent.

## Dev-only worker contract

- The brief outranks every default in `/we:develop`. The worker names each override in its report.
- A brief never overrides a stop. The worker stops and reports `blocked` when the plan carries an
  unanswered `## Open Fork` (`references/story-plan.md` § Readiness), when a ticket comment changes the scope after the plan, when the same
  gate fails three times, or when the work needs a product decision, a money-path redesign or a
  foreign subsystem's redesign.
- The worker never opens a PR, runs or waits for CI, moves or creates a ticket, merges into the
  default branch, or edits files outside its chunk. It pushes only when the brief says `Push: yes`, or when the Lead
  says a quota end is near: then it commits its phase and pushes it to `wip/<KEY>-<slug>`. Every push
  is preceded by the conflict check of `/we:ci-review` § 3 (merge `origin/<default-branch>` only on a conflict).
- No wait loops and no `sleep` in the foreground: the auto mode holds them as a permission prompt. Wait on
  CI with `watch-pr-checks.sh` or `gh pr checks --watch` in the background, or for the notification;
  never poll a task file with `tail`/`cat` (a process worker's card says the same: `roles/worker.md`).
- The worker reads and searches with the Read, Grep and Glob tools on absolute paths, never with
  `cd <dir> && grep …` or `cat`/`rg` through Bash: a compound `cd` asks for permission and leaves the
  worker in a tree that is not its own; git runs as `git -C <worktree> …`.
- The worker implements the plan's phases in order, inline, and never fans implementation out to
  sub-agents: one worktree has one git index, and a second committer races `.git/index.lock`.
- The worker commits per phase and stages by path, never `git add -A`. Every commit carries
  `Co-Authored-By: <Model> <noreply@anthropic.com>` for the model actually running; the Lead never
  re-signs a worker's commit.
- Local gates: the repo's linter, formatter and type-checker on the changed files, plus only the
  tests the change affects (importers of the touched code, its callers' tests, the contract suites
  when a route or boundary changed). Never the whole suite; CI runs it. A test needing a database or
  a network service is skipped and listed, unless the brief names an integration suite for a
  critical chunk (money, auth, tenant isolation, migration): then the worker runs it and quotes the
  last 20 lines in the report.
- A gate run that ended without a verdict, and the other measured traps of shared trees:
  `references/session-traps.md`; only a run the worker answered with a fix runs again.
- A mutation run the plan or repo asks for happens inside the chunk, right after its seam tests are
  green and before the report, never as a step after the PR: run after a green PR it cost a second
  CI round and let a parallel migration land first (64 of 201 min, 17.10.2026).
- Finish first: a finding of at most ~30 min on the seam the chunk touches gets fixed in the same
  branch; "pre-existing" is no reason to defer. A money-path finding gets its own commit and a
  question, so the Lead can revert it. The worker never creates tickets.
- No local LLM review (no `code-review`, `simplify`, `security-review`, no reviewer agent): CI runs
  the Claude and Codex reviews on the PR, and on 01.10.2026 local QA cost 5.3M tokens against 4.4M
  for building, for few real findings. The one exception is a critical chunk: the Skill tool's
  `code-review` with `args: "high <worktree path>"` once over the branch (the skill forks into a
  fresh context and reviews the session's directory unless `args` names the path). A review whose
  findings name no file from `git diff --name-only origin/<default-branch>...HEAD` ran on the wrong
  tree: run it again. Fix BLOCKING and WARNING, commit, report the counts.

## Finish sequence (the last writer, before the first push)

The session or worker that writes last on the PR branch runs this once over
`git diff origin/<default-branch>...HEAD`, committing after each step:

1. The deterministic gates over the finished branch, not after an intermediate commit: the full local gate script the
   repo's instruction files name (it runs the pre-push and manual stages), else `pre-commit run --hook-stage pre-push
   --from-ref origin/<default-branch> --to-ref HEAD` plus `pre-commit run --hook-stage manual <id> --from-ref
   origin/<default-branch> --to-ref HEAD` per manual hook marked as a CI mirror (the diff range, because `--all-files`
   runs every hook past its path filter over the whole tree); and the affected tests by name, except a test whose
   last green run in this session was on the current HEAD.
2. Only when the diff touches money, auth, tenant isolation or a migration: the contract's
   `code-review` at `high` through the Skill tool, never as a slash command written into a subagent
   prompt (not proven to run the skill, probe 27.09.2026). No other LLM review.
3. Verification against a running instance when the brief orders it, per `.weside/verify.md`: DEV
   only (staging is a question to the human). The receipt goes into the plan's `## Verification`
   with the four literal labels `**Oracle:**`, `**Seed:**`, `**Asserted:**`, `**Not proven:**`.
   `not-applicable` and `not-observed` are valid only with their reason
   (`references/story-plan.md` § Verification); a run that did not happen is
   `not-observed`, never a filled receipt.
4. Only the deviations from the plan recorded in the plan (`references/story-plan.md` § Lifecycle).
5. The affected gates again when step 2 or 3 moved code.

No step's output is the final message; the turn ends with § Report (the plugin's `SubagentStop`
hook sends a dev worker that stopped early back to work).

Before starting a server, check who owns the single-owner ports (`ss -ltnp`, then
`ls -l /proc/<pid>/cwd`): `(deleted)` is an orphan and yours to clear; a live cwd in your worktree
is yours; a live cwd in another worktree belongs to another session, and you ask instead of
killing. PPID 1 is normal for a detached dev server and proves nothing. Stop your server by PID,
children included, the moment verification ends.

## Card worker

A check an owner's card assigns to a fresh worker (a `trust-loosening` signature, a seam or migration check, an
acceptance walk; L0 § Against the waterfall) runs as a read-only worker the master starts like any other
(§ Worker launch backend). Its brief carries, under the four headings of § Name and brief:

- **The card:** the output of `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/render_process.py --role <role>` in the repo, pasted
  verbatim; the worker reads no other copy.
- **The card version:** `we <version>` from `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. A card changes only
  with a plugin release, so the version names the revision the verdict was judged by; the verdict quotes it.
- **The case:** the diff or the screen, the relevant ADRs, and precedent PRs with their verdicts.
- **The exit:** a case without precedent is reported to the owner undecided; the worker never decides it.

The verdict goes on the PR or the board item, never into a ticket the worker files. A security card
verdict on a card hit is a PR comment in the form `automerge_gate.py` reads (its docstring, refusal 5):
the marker `<!-- security-card-review -->`, the heading `## Security card review — #<N> @ \`<head sha>\``
and `**Overall: PASS**` or `BLOCKING`; only a PASS on the current head lets the merge through.

## Lead checks around a worker

### Premise check

Before dispatch, the Lead verifies every factual premise of the brief against
`origin/<default-branch>` (a file still says X, N rules lack Y, a function exists) and keeps the
command that showed it. A count from a heuristic script goes into the brief as an estimate
(`~19, heuristic`) for the worker to confirm before acting on it. 2026-10-02: a brief's "~19 rules
lack nested globs" was 2, and a "still names the old model" was already fixed on main; the worker
spent its time disproving the brief.

### Code graph in the brief

Where `.weside/config.json` → `tools.graphify` is true, the brief decides the code-graph question per
chunk and names the symbols, because workers act on the brief, not on the repo rule: in a 10-day sweep
(10/2026) workers whose brief named the graph used it in 33 of 55 runs, the others in 26 of 399.

- The chunk changes a symbol that is called from outside its own file → `graphify affected "<symbol>"
  --relation calls --depth 2` before the edit; the worker reports the caller count.
- The brief or question names a behaviour but no file → the repo's graph query (its instruction files
  name the command) first, `rg` to confirm.
- A known file or a literal string → `rg`; the brief says `Code graph: not needed (<reason>)`, so a
  retro can judge the call.

### Watchdog

Armed at dispatch, one per worker: `${CLAUDE_PLUGIN_ROOT}/scripts/watch-worker.sh <wt> <name>` as
a background command. It exits on the first event (a commit, a 25-min stall, the worktree gone, a
25-min lifetime cap); its header lists the lines and exit codes. Re-arm it in a Bash call of its own
with `run_in_background: true`, never `&` or `disown` in a foreground call: a detached watchdog
sends no notification and survives the next one (twice on 15.10.2026). When the worker's report
arrives or the worker is stopped, `TaskStop` its watchdog by task id in the same turn, never by a
`pkill` pattern: a leftover watchdog later reports a stall that is not real (three on 17.10.2026).

A commit becomes one status line to the human (phase done). A stall gets evidence (`git log -3`,
`git status`, the agent's state) before any word about it. Three runs with it had 0 idle nudges
by the human (#4308, #4326, #4328); without it a worker sat idle 7 h 47 min (#4299).

### After each lane merge

In the integration tree: the repo's type-checker on the files the merge changed (`git -C <int> diff --name-only HEAD^1 HEAD`) and the tests that import them (`rg -l` over
the changed module names in the test trees). Red → fix before the next merge. Skipping it cost 14
red tests at the finisher on #4310.

## Report

A subagent's final message is the report, and the Agent result delivers it; a process worker sends
it as one `SendMessage` to its `Lead:` (§ Worker launch backend). Fields:

```
branch: <name> · worktree: <path> · commits: <n> · pushed: yes|no
gates: <command> @ <short HEAD sha> → <its result line> | skipped(<why>) …   (the receipt the Lead reads instead of re-running)
ACs: <AC id> → <test name or file:line> …   (one line per AC the chunk claims)
code graph: <symbol> → <n> callers … | not needed (<reason>)   (when the brief has a Code graph line)
review: code-review high <found> found · <fixed> fixed · <skipped> skipped (<why>) | none (not critical)
finish sequence: done|not ordered · verification: <oracle + receipt location>|not ordered
retired: <old test> → <new-seam test> …   (refactor chunks; none|<reason> when nothing retired)
overrides: … · skipped: … · questions: … · blockers: none|<reason>
```
