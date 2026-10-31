---
name: worker-dispatch
description: How the Lead picks and dispatches a dev worker, the dev-only worker contract, the finish sequence before the first push, and the report. Shared by /we:orchestrate and /we:develop.
---

# Worker dispatch

## Contents

Choosing the worker · Worker launch backend · Dev-only worker contract · Finish sequence · Lead checks around a worker
(premise check, code graph in the brief, watchdog, lane merge) · Report.

The Lead (`/we:orchestrate`) dispatches; the worker (`/we:develop`) obeys the contract below. A
worker cannot rely on reading this file: the Lead's brief carries every rule the chunk needs.

## Choosing the worker

- Dispatch shape: § Worker launch backend; the default is `Agent(name=…, subagent_type="we:dev-medium" | "we:dev-high", isolation="worktree", description=…, prompt=<brief>)`.
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
- Timing: the plugin hook `hooks/subagent_timing.py` appends one line per `SubagentStart`/`SubagentStop` (`ts`, `event`, `agent_id`, `agent_type`, `cwd`) to `~/.claude/we-timing/<session_id>.jsonl`, the measurement for comparing orchestration approaches; the same file gets `InstructionsLoaded` and skill-run lines for `/we:retro` and `/we:instruction-audit`.

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

`.weside/config.json` → `agents.worker_launch` decides how every `we:dev-*` worker starts:
implementer, finisher, refiner, a ci-review worker. `we:explore-medium` readers and council lenses
stay subagents. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/worker_launch.py backend` prints the setting.

- `"subagent"` (the default, also when unset): the `Agent` call of § Choosing the worker. A
  subagent bills the account of the session that calls it.
- A command template: each worker is a session of its own, billed to the login the command starts
  it on. Placeholders, each a token of its own: `{name}` (required), `{brief}` (required; becomes
  `Read <git-dir>/we-brief.md and follow it.`), `{agent}` (the `we:dev-*` agent, as `--agent
  {agent}`, so its effort and model apply). Example: `"claude --bg -n {name} --agent {agent}
  {brief}"`. The command starts the worker in the Lead's permission mode, or Claude Code may hold
  the Lead's messages for approval.

With a template, the Lead:

1. Creates the worktree: `git fetch origin`, then `git worktree add <repo>-<KEY>[-p<N>] -b
   <type>/<KEY>-<slug> origin/<default>`; the branch carries its final name, no rename. A finisher
   or ci-review worker launches in the existing tree. `claude --bg` refuses an untrusted directory;
   a worktree of a trusted repo is trusted (measured 31.10.2026), a fresh scratch repo is not.
2. Writes the brief to a file and runs `worker_launch.py launch --worktree <wt> --name <name>
   --agent <we:dev-…> --brief-file <file>` (`--agent` is required when the template has `{agent}`). It appends `Lead: <this session's name>` to the brief
   (an unnamed Lead is refused: `/rename <KEY>` first), writes the marker `we-worker.json` into the
   worktree's git dir and runs the command there.
3. Subscribes with `notify_when_idle: true` on its first message to the worker, again on each
   steer. A steer is `SendMessage(to=<name>)`, as for a subagent.
4. Arms the watchdog (§ Watchdog). Its exit 4 `exited: <name>` means the session ended: read the
   report, else `claude logs <name>`.
5. Stops the worker with `worker_launch.py stop --name <name> --worktree <wt>` instead of
   `TaskStop`, once its report is integrated or dropped, also after exit 4: it removes the marker
   and the brief, then the worktree can go or the Lead can work in it.

The hooks treat a session as the worker only when the marker names its session id, so the Lead
working in the worker's tree is never one.

The worker reports by one `SendMessage` to its `Lead:`; its plain text never reaches the Lead. The
Stop hook `worker_report_gate.py` blocks a turn without that message, and `automerge_gate.py`
refuses its merge as for a subagent.

## Dev-only worker contract

- The brief outranks every default in `/we:develop`. The worker names each override in its report.
- A brief never overrides a stop. The worker stops and reports `blocked` when the plan carries an
  unanswered `## Open Fork`, when a ticket comment changes the scope after the plan, when the same
  gate fails three times, or when the work needs a product decision, a money-path redesign or a
  foreign subsystem's redesign.
- The worker never opens a PR, runs or waits for CI, moves or creates a ticket, merges into the
  default branch, or edits files outside its chunk. It pushes only when the brief says `Push: yes`, or when the Lead
  says a quota end is near: then it commits its phase and pushes it to `wip/<KEY>-<slug>`. Every push
  is preceded by `git merge origin/<default-branch>` and the after-merge check (`/we:ci-review` § 3).
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
- A gate run that ended without a verdict (killed, aborted, timed out, out of memory, a worker pool
  that broke) is never restarted automatically, neither by the worker nor by a loop or a monitor: the
  worker reads why it ended and reports it, and only a run it has answered with a fix runs again. On a
  shared host the cause is usually another heavy run; a second start doubles the load (30.10.2026:
  restarted gate runs took a shared host past its memory limit twice).
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
   (`skills/story/references/plan-format.md` § Verification); a run that did not happen is
   `not-observed`, never a filled receipt.
4. Only the deviations from the plan recorded in the plan (`skills/story/references/plan-format.md` § Lifecycle).
5. The affected gates again when step 2 or 3 moved code.

No step's output is the final message; the turn ends with § Report (the plugin's `SubagentStop`
hook sends a dev worker that stopped early back to work).

Before starting a server, check who owns the single-owner ports (`ss -ltnp`, then
`ls -l /proc/<pid>/cwd`): `(deleted)` is an orphan and yours to clear; a live cwd in your worktree
is yours; a live cwd in another worktree belongs to another session, and you ask instead of
killing. PPID 1 is normal for a detached dev server and proves nothing. Stop your server by PID,
children included, the moment verification ends.

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
