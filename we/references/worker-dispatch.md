---
name: worker-dispatch
description: How the Lead picks and dispatches a dev worker, the dev-only worker contract, the finish sequence before the first push, and the report. Shared by /we:master and /we:develop.
---

# Worker dispatch

## Contents

Choosing the worker · Worker launch backend · Dev-only worker contract · PR-carrying worker · Finish sequence · Card worker · Lead checks around a worker
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

### What `isolation: "worktree"` does (Claude Code 2.1.283)

- The worktree branches from `origin/<default-branch>` (setting `worktree.baseRef`, default
  `fresh`). Run `git fetch origin` before the dispatch, or the worker starts from a stale base.
- The branch is named `worktree-<name>` with `/` rewritten to `+`. The worker renames it to the
  branch the brief names before its first commit.
- `isolation` and `cwd` are mutually exclusive. A worker for an existing tree (the integration
  worktree) gets `cwd=<path>` instead.
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
  {agent}`, so its effort and model apply), `{lane}` (`--utility` for `launch --utility`, nothing
  for a build start; a `we-worker` template only: a `claude` template with it is refused, its
  worker's settings file carries the lane). Example: `"claude --bg -n {name} --agent {agent}
  {brief}"`. The command starts the worker in the Lead's permission mode, or Claude Code may hold
  the Lead's messages for approval. With `we-worker`, the crew's `launch.worker_mode: bypass` starts
  a `--bg` worker in bypass (`default`: no `--permission-mode`), a window worker keeps its default
  mode; `launch.allow_bypass: true` adds `--allow-dangerously-skip-permissions`, and in a repo
  without a crew `WE_WORKER_ALLOW_BYPASS=1` does (a crew's value always wins): in the background
  nobody answers a prompt, and the `permissions.deny`/`ask` rules and the plugin's guards still
  hold under bypass.

### Name and brief

`we-worker` and `worker_launch.py launch` refuse a start (exit 2, before any file or session) whose
name does not start with the story key (crew `naming.key`, `<KEY>-<chunk>`; `worker_launch.py check`,
its docstring owns the grammar), and a start without a brief (the last argument; a `--resume` needs
none), with `--bg` or `--queue`, where nobody hands the task in later; a window worker may
start empty. The brief's shape is not checked. A brief carries four Markdown
headings, each with a body: `Ziel`/`Goal`, `Ausgabe`/`Output`, `Werkzeuge und Quellen`/`Tools and
sources`, `Grenzen und wann stoppen`/`Limits and when to stop`. Its last line is
`Worker: <name> · started-by <starter>`: the worker signs its commits and PR body with the same line
plus its session id (§ Dev-only worker contract, **Signature**).

- Bad: `we-worker AB-12-fix --bg "fix the login bug"`: the worker guesses the tree, the end and whom to tell.
- Good: `## Goal` the login refuses an expired token, plan `docs/plans/AB-12-story.md` · `## Output` one
  commit on `feat/ab-12`, report to the Lead by `SendMessage` · `## Tools and sources` this worktree,
  `pytest tests/auth` · `## Limits and when to stop` no push, no migration; stop after the commit ·
  `Worker: AB-12-fix · started-by ab-master`.

Every denial of the worker rights brake is one line in `<state dir>/brakes.jsonl`
(`worker_rights.brake_log`): the count of false alarms. A crash of the brake is a defect, not a
brake: it fails open with one `crash` line (the exception's class, never its message), and denies only the hard items
(`worker_rights.HARD`: secrets, deletion, a push to main, a merge past the checks).
`check` names a living session of the same key on stderr: a follow-up goes to it by `SendMessage`.
After the check `we-worker` refuses a start (exit 3, nothing starts) while a queued start of any
repo waits ahead of it, while the busy workers on the machine (background sessions and window
workers; interactive companions and masters never count, nor a worker whose state is `done`: its
report is in and it works no more) reach the lane's pool limit (§ Utility lane below), or while
no account in the rotation (`cswap list --json`) has room: 7d under 95 % and 5h at or under
`max_active_5h_percent`; one account with room lets the start through, the rotation
switches to it. Without the list the active account's 5h decides; without `cswap` the check is
skipped (`worker_launch.py capacity` owns the rule); there is no override flag. Both limits are
the machine's, because the busy count is: `<state dir>/pool.json`
`{"max_busy_sessions": N, "max_active_5h_percent": P}` (defaults 8 and 80), one file for every repo
on the host; `worker_launch.py pool-path` prints where it lies (`$WE_WORKER_STATE_DIR` first). A
repo's `workers` block may only lower either value; one above the machine's is not read. A queued
start that only its repo's lower value holds back stays first in line and lets other starts pass
while the machine has room.
`we-worker <name> --bg --queue [--queue-timeout 2h]` queues a refused start instead: a detached
waiter starts it once the check passes, first come first served across every repo, gives it its
own worktree when it was queued from a main checkout, and tells the starter one line when it
starts, fails or times out; `we-worker status` lists queued starts, `we-worker stop <name>` removes
one (`scripts/worker_supervisor.py`, the comment above `queue_dir`). A queued start reads its brief
only when it starts: `we-worker amend <name> --brief-file <f>` replaces it while it waits,
`we-worker prio <name> --first|--after <other>` moves it in its lane, and `we-worker start-now
<name> --reason "<the human's word>"` starts it at once past the cap and the room rule, never past the accounts' quota (one
`override` line in `brakes.jsonl`). A `--queue` start runs as a background command
(`run_in_background: true`), never behind a shell `&`; `we-worker status` comes before a second
start of the same name. The launcher's own flags count in any position before the brief, and a
refused start prints `we-worker: NOT STARTED: <name> …` on stdout as well: a launch whose output
goes through a filter checks that line or the exit code (`we-worker … >log 2>&1; echo "rc=$?"`),
never only a `grep` for the started line. A worker blocked on the
host's test slot (`scripts/slot_lock.py`, the slot's one holder and reader) shows
`waits: test-slot` in `we-worker status`: it counts as busy, holds its memory and does no work.

**Utility lane.** `we-worker <name> --utility …` starts a worker that keeps work already underway
moving: a fix round on an open PR's branch, a card, lens or review worker; a refiner, a read-only
measurement and a fast-lane fix (no plan file, one repo, one script and its test) start there too,
as light workers (no test suite, gate or build of their own) that never wait behind full builds.
Other build work starts without the flag. A utility start counts the utility lane's busy workers against `pool.json`
`max_utility_sessions` (default 5; a repo may lower it), never against `max_busy_sessions`, and with
`--queue` it waits in its own queue: a fix round never waits behind new build work (measured
22.11.: one waited over an hour). The 5h check holds for both lanes. A worker belongs to the lane
it started in (`WE_WORKER_LANE` in its settings file, `lane` in its marker and `launched.jsonl`
line). The master starts a utility worker with `worker_launch.py launch --utility` (the template's
`{lane}`); a full build never.

**Room on the machine.** A start of either lane that passes its cap also needs room, both or
it waits (Kiska, 22.11.: the host's memory guard killed workers six times at 94 % working set, four
of them at 10 workers, each set off by one tsc or pytest peak of 2 to 2.5 GiB): the own cgroup's
working set (`memory.current − memory.stat file + memory.stat shmem`) below
`max_working_set_ratio` (0.84, a share: 0 < r ≤ 1) of `memory.max`, or of MemTotal in `/proc/meminfo` when the limit
reads `max`; `memory.pressure` `full avg60` below `max_pressure_full_avg60` (1); each a `pool.json` key of the machine. A missed condition is no refusal: the
start exits 4 and a `--bg` start waits in its lane's queue, `--queue` or not, naming the missed
condition with its value and threshold; the queue's waiter checks the same rule before it tries
(`worker_launch.resources`, `worker_supervisor.machine_room`). A window start cannot wait and exits
4. A file it cannot read (no cgroup v2) counts as met and shows `n/a`; `we-worker status` ends with
the room for both lanes. A queued start whose waiter died (a crash, a pod restart) starts nothing:
`we-worker status` marks it `dead waiter`, and `we-worker status --restart-waiters` starts a new
waiter; the entry keeps its place and deadline.

### Worker rights

Every `we-worker` start passes `--settings` (`worker_launch.py settings`: the repo's granted rights
as `permissions.allow`, the never-list as `permissions.deny`, the worker's variables as `env`,
`worker_rights.worker_env`). A `claude --bg` session takes the daemon's environment, not the
launcher's, so a plain `claude --bg` template gets an env-only `--settings` too
(`we-worker.settings.json` in the worktree's git dir). Every `claude` call of `worker_launch.py`
drops `CLAUDE_CONFIG_DIR`, so a pinned master sees the global login's sessions.
`we-worker --account auto|<name>` asks the project's `agents.accounts_command` for the account
(`<cmd> --need critical|uncritical`, critical unless one of the brief's first ten lines is
`Account: uncritical`) and puts its `env` and its `token_command` as `apiKeyHelper` into that settings
file (mode 0600), never a secret on a command line and never a `CLAUDE*` (but the CLI's `CLAUDE_CODE_*`), `WE_*` or `WESIDE_*` variable; a critical worker on a non-Claude account refuses (`worker_launch.py choose_account`).
The brake is the PreToolUse hook `hooks/worker_rights_gate.py`, which holds under `bypassPermissions`:
a worker runs `gh pr ready` (or `pr_ready.sh`), `gh pr comment` and the crew's `branch_rc` without
asking; a `gh pr merge` is judged by the merge line; every worker is denied the never-list (secrets,
delete, `main`, a commit past the secret scan). Rules and limits: `scripts/worker_rights.py`
(its docstring). A denial names the Lead; the worker reports it and the Lead acts. It catches a slip, it is no
boundary: a script file passes it.

### Tree, context and end (`we-worker`)

A `we-worker <name>` start picks the worker's tree in one of three modes (`we-worker --help` owns
the flags, `worker_launch.py tree` the rule). `.weside/config.json` `workers.tree` decides what a start
without a flag does: `caller` (default) stays where the caller stands and, from the main checkout,
prints a tip; `own` gives a start from the main checkout its own tree.

| Mode | When | Tree |
|---|---|---|
| own tree | a build worker started from the main checkout under `workers.tree: own`, and every `--queue` start from the main checkout | a new worktree beside it: `.weside/config.json` `workers.add_worktree` (a template with the tokens `{path}` and `{branch}`), else `git worktree add <repo>-<name> -b feat/<name> origin/<default>`; `--branch` names the branch |
| `--tree <path>` | an integration worktree, a finisher, a fix round | that existing worktree |
| `--here` | a worker that only reads: probe, walk, card, pre-sorter | where the caller stands |

A start from a linked worktree or outside a repo, and a `--resume`, stay where they are, as does
every start through `worker_launch.py launch` (its cwd is the Lead's worktree). The launcher prints
the tree; a created or named tree gets the marker `we-worker.json` with name, key, role, starter,
tree and mode, which `/board` shows on the worker's line.

`workers.context` in `.weside/config.json` makes the worker's settings lean; without the block the
file stays rights and `env` only. Keys (`worker_launch.py apply_context` owns them):

| Key | Settings |
|---|---|
| `auto_memory`: `off` (default) · `own` · `shared` | `env.CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` · `autoMemoryDirectory` `<state dir>/<name>.memory` · the repo's memory |
| `disable_plugins: ["<plugin>@<marketplace>"]` | `enabledPlugins: {<id>: false}` |
| `deny_mcp_servers: ["<server>"]` | `deniedMcpServers: [{"serverName": <server>}]` |
| `auto_compact_window: <tokens>` | `autoCompactWindow` (100000–1000000) |

A brief that needs a tool says so in one line, `Needs: <plugin or MCP server>, …`; when
`disable_plugins` (by id or bare name) or `deny_mcp_servers` turns one of them off, the start
refuses (exit 2) and names it, instead of a worker that silently lacks it (`worker_launch.py
needs`). The same holds for every `/we:<skill>` the brief names: a skill declares its needs in its
frontmatter (`needs: [<plugin or MCP server>, …]`; `ticketing` is the project's ticketing plugin,
`references/ticketing.md`), and the refusal names the skill and the plugin. A brief needs no
`Needs:` line for what its skills declare.

A brief that names `/we:<skill>`s (directly or in the file of its `Read <path> and follow it.`
line), none of which needs `ticketing`, starts without the ticketing plugin (`enabledPlugins`
false, else `deniedMcpServers`; `worker_launch.py ticketing_unneeded`): its tools cost every cold
start about 2.7k tokens, and most build and fix workers never touch a ticket; `Needs: ticketing`
keeps it, a brief without a skill keeps every tool.

Every variable the launcher decides stands in the file's `env`, a cleared one as `""`
(`worker_rights.worker_env`): a `--bg` session inherits the daemon's environment, never the
caller's shell.

Each start also starts the supervisor, which tells the starter about a worker's stop and cleans up
after it, names a long-`blocked` worker to its starter, names one whose turn or process ended
without its report, and stops an idle one whose report is in (`workers.blocked_notify_minutes`,
`workers.unreported_notify_minutes`, `workers.idle_stop_minutes`; its docstring owns the rules); `we-worker close <KEY>` is the one closing step after a merge (In Review, teardown, the
epic's log line; `scripts/worker_close.py`, whose docstring owns its holds: a living or queued
worker on the key, no story plan, an unbuilt phase). `we-worker gc` removes what dead sessions left
(`scripts/worker_supervisor.py`'s docstring owns both and the end reason `we-worker status` prints).
`we-worker stop` prints the worker's session id and resume command: `we-worker <name> --bg --resume
<name>` (its kept `<name>.resume.json`, 7 days) or `--resume <id prefix>`. Copy a stopped tree's
untracked files (`git -C <tree> status -s`) to the scratchpad before removing it; a reversed stop
recreates the tree at its path, copies them back and resumes with a steer naming the new scope.

With a template, the Lead:

1. Creates the worktree: `git fetch origin`, then `git worktree add <repo>-<KEY>[-p<N>] -b
   <type>/<KEY>-<slug> origin/<default>`; the branch carries its final name, no rename. A finisher
   or ci-review worker launches in the existing tree. `claude --bg` refuses an untrusted directory;
   a worktree of a trusted repo is trusted (measured 31.10.2026), a fresh scratch repo is not.
2. Writes the brief to a file and runs `worker_launch.py launch --worktree <wt> --name <name>
   --agent <we:dev-…> --brief-file <file>` (`--agent` is required when the template has `{agent}`;
   `--utility` for a member of § Utility lane). It puts `Lead: <this session's name>` as the brief's first line
   (an unnamed Lead is refused: `/rename <KEY>` first), writes the marker `we-worker.json` into the
   worktree's git dir and runs the command there.
3. Subscribes with `notify_when_idle: true` on its first message to the worker, again on each
   steer. A steer is `SendMessage(to=<name>)`, as for a subagent. A steer that adds work asks for a
   one-line pickup reply; none within one watchdog interval → stop the worker and start a fresh one
   from the full brief file, never a second steer (a worker that lost its brief answers no steer).
4. Arms the watchdog (§ Watchdog). Its exit 4 `exited: <name>` means the session ended: read the
   report, else `claude logs <name>`.
5. Stops the worker with `worker_launch.py stop --name <name> --worktree <wt>` instead of
   `TaskStop`, once its report is integrated or dropped, also after exit 4: it removes the marker
   and the brief, then the worktree can go or the Lead can work in it.

The plugin ships a launcher: `scripts/we-worker` (installed next to `wclaude` by
`scripts/install_launcher.py`; `we-worker --help`), with the verbs
`status|stop|logs|waiting|checkpoint|is-worker|close`; `worker_launch.py stop` uses its `stop` when the template
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
Stop hook `worker_report_gate.py` blocks a turn without that message. A worker never
arms; it may run the ready merge line `arm_pr.sh` prints (the worker card).

## Dev-only worker contract

- The brief outranks every default in `/we:develop`. The worker names each override in its report.
- A brief never overrides a stop. The worker stops and reports `blocked` when the plan carries an
  unanswered `## Open Fork` (`references/story-plan.md` § Readiness), when a ticket comment changes the scope after the plan, when the same
  gate fails three times, or when the work needs a product decision, a money-path redesign or a
  foreign subsystem's redesign.
- The worker never opens a PR, runs or waits for CI, moves or creates a ticket, merges into the
  default branch, or edits files outside its chunk (a brief with `PR owner: worker` hands it the PR:
  § PR-carrying worker). It pushes only when the brief says `Push: yes`, or when the Lead
  says a quota end is near: then it commits its phase and pushes it to `wip/<KEY>-<slug>`. Every push
  is preceded by the conflict check of `/we:ci-review` § 3 (merge `origin/<default-branch>` only on a conflict).
- No wait loops and no `sleep` in the foreground: the auto mode holds them as a permission prompt. Wait on
  CI with `watch-pr-checks.sh` in the background (the one wait: quota, lock and interval floor), or for the notification;
  never poll a task file with `tail`/`cat` (a process worker's card says the same: `roles/worker.md`).
- The worker reads and searches with the Read, Grep and Glob tools on absolute paths, never with
  `cd <dir> && grep …` or `cat`/`rg` through Bash: a compound `cd` asks for permission and leaves the
  worker in a tree that is not its own; git runs as `git -C <worktree> …`.
- The worker implements the plan's phases in order, inline, and never fans implementation out to
  sub-agents: one worktree has one git index, and a second committer races `.git/index.lock`.
- The worker commits per phase and stages by path, never `git add -A`. Every commit follows the
  repo's commit format and carries `Co-Authored-By: <Model> <noreply@anthropic.com>` for the model
  actually running, unless the repo's instructions or hooks refuse attribution; the Lead never
  re-signs a worker's commit.
- **Signature.** A process worker's commit message and PR body end with one line naming who made
  them, so the human sees from which worker a PR comes: `Worker: <name> · <session-id> · started-by
  <starter>`, from `$WE_WORKER_NAME`, `$CLAUDE_CODE_SESSION_ID` and `$WE_STARTER` (`we-worker` sets
  the names in the worker's settings file; `-` for an empty one). It is the last line, below the
  trailers above.
  - Bad: `Co-Authored-By: …` alone: three workers on one story read the same.
  - Good: `Worker: AB-12-fix · 0f3c9a1e-… · started-by ab-master`.
- Tests: only the ones `references/test-economy.md` asks for (which defect does this test catch
  that no existing test catches?); no test per endpoint, page or review round by default.
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
  question, so the Lead can revert it. Follow-ups (worker, Lead, review round) are named in the report
  with a recommendation, never ticketed unless the user asks, and nobody asks whether to file one: a
  ticket nobody asked for is work for the product owner, a named follow-up lets the human decide.
- No local LLM review (no `code-review`, `simplify`, `security-review`, no reviewer agent): CI runs
  the Claude and Codex reviews on the PR, and on 01.10.2026 local QA cost 5.3M tokens against 4.4M
  for building, for few real findings. The one exception is a critical chunk: the Skill tool's
  `code-review` with `args: "high <worktree path>"` once over the branch (the skill forks into a
  fresh context and reviews the session's directory unless `args` names the path). A review whose
  findings name no file from `git diff --name-only origin/<default-branch>...HEAD` ran on the wrong
  tree: run it again. Fix BLOCKING and WARNING, commit, report the counts.

## PR-carrying worker

`.weside/config.json` `build.pr_owner` (`worker_launch.py pr-owner`) says who carries a build PR.
`master` (the default): the worker ends with § Report and the master pushes, opens, arms and watches
(`/we:master` § Push, PR, CI). `worker`: the master writes the line `PR owner: worker` into the brief
of a story's single build worker, or of the finisher in a parallel story's integration tree; a
parallel chunk never gets it, the master integrates its branch as before. The line is the switch a
worker reads, and its push: without it, it runs the dev-only contract and never guesses from the config.

With the line, after § Finish sequence the worker carries its PR itself, because a hand-off to the
master costs a round trip per head and the master's context:

1. Push once and open the PR with `/we:pr`.
2. The class and the arm per `/we:master` § Close the run (who merges what): `arm_pr.sh <PR>`, acting
   on its final line as that table says (`ready` → the printed `gh pr merge … --match-head-commit`).
   One-way, a hold label or a draft reason → no arm: `held`. Under `merge.armer: workflow` the
   repo's workflow arms the ready PR and `arm_pr.sh` refuses: the end is `armed` without an arm.
3. Red checks or review findings → `/we:ci-review`: one push per head, at most three rounds, a repeat
   finding stops (`held`).
4. The § Report, its last line exactly one of:

```
armed: <PR> on <sha>       armed and green or waiting for checks; GitHub merges, the worker ends
held: <PR> (<why>)         one-way, hold label, draft, a human decision, the round cap; the PR is the starter's
parked: <branch> (<why>)   time limit, quota or a stop: checkpoint pushed to wip/<KEY>-<slug>, the resume command in <why>
```

The starter acts on that line alone: `armed` → `watch-pr-checks.sh <PR> --sha <sha> --until-merged`
(an event-routed master: no watcher, the PR's `merged` line; `references/session-traps.md` § CI and checks),
on its merge (`merged`, `merged-green`) `/we:merged <PR>` (it runs `we-worker close <KEY> --pr <n>`), on
`merged-red` (exit 15) the fix first; `held` → the PR continues
at `/we:master` § Push, PR, CI step 5 or the one-way row; `parked` → resume per the line. The Stop
hook `worker_report_gate.py` sends a report with any other last line back once.

Rights: under `worker` the settings allow the push, `gh pr create`, `gh pr edit` and `arm_pr.sh`
without a prompt; the gate judges only `arm_pr.sh` (with `WE_ROLE=worker`), a `gh pr edit` removing a
hold label, and for every owner `gh pr merge` as `--disable-auto` or the `--match-head-commit <checkout
HEAD>` line while `arm_pr.sh --check` answers `ready` (`scripts/worker_rights.py`, its docstring); the
never-list stays denied. A worker started in the main checkout pushes only as one `git -C <own worktree> push …`, without `2>&1`, `&&` or a second segment, because only that form names the tree the gate checks.

## Finish sequence (the last writer, before the first push)

The session or worker that writes last on the PR branch runs this once over
`git diff origin/<default-branch>...HEAD`, committing after each step:

1. The affected tests by name over the finished branch, except a test whose last green run in this
   session was on the current HEAD. The static gates run once, in the pre-push hook of the push and
   again in CI: never by hand before it.
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
acceptance walk; L0 § Against the waterfall) runs as a read-only worker the master starts with `launch --utility`
(§ Worker launch backend). Where it runs as a subagent (the backend's fallback, a repo without a crew), it is
`we:dev-medium` with a read-only brief, never `we:explore-medium`: it needs Write for its output file and
SendMessage for the path. Its brief carries, under the four headings of § Name and brief:

- **The card:** the output of `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/render_process.py --role <role>` in the repo, pasted
  verbatim; the worker reads no other copy.
- **The card version:** `we <version>` from `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. A card changes only
  with a plugin release, so the version names the revision the verdict was judged by; the verdict quotes it.
- **The case:** the diff or the screen, the relevant ADRs, and precedent PRs with their verdicts.
- **The exit:** a case without precedent is reported to the owner undecided; the worker never decides it.

The verdict goes on the PR or the board item, never into a ticket the worker files. A security card
verdict on a card hit is a PR comment for the human and the security owner, read by people, in this
form: the marker `<!-- security-card-review -->`, the heading ``## Security card review — #<N> @ `<head sha>` ``
and `**Overall: PASS**` or `BLOCKING`. It is no merge condition: whether it stands before a merge is
the merger's judgment.
The card worker never posts it: `worker_rights_gate.py` denies a worker a comment on a PR that is not
its own branch's. It writes the verdict to the file its brief names under `## Ausgabe`/`## Output` (marker,
heading with the head sha, `Overall:` last) and sends the path to its starter. **The starter posts the
card verdict**, whichever session started the worker (a Lead, the coordinator, a platform session):
it checks the marker, the sha against the PR's current head and the file's mtime against the
worker's start, then posts the file unchanged with `gh pr comment <N> --body-file <file>`. The worker judged, the starter only passes the verdict on, so this does not go
around `worker_rights_gate.py`; never start a second worker only to post (owner decision, 13.11.2026).

A one-way PR's merge question goes onto the board once the card verdict for its head is in, until then
`waiting: card` (`board.py set now=…`): a PR merged before its card needed a follow-up PR. The card is
input, not a gate (security owner, 18.11.2026). Right after the post the starter:

- logs the verdict: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/worker_rights.py brake card --pr <N> --file <file>`
  (one `card` line in `brakes.jsonl` with `verdict` and `pr`);
- on `BLOCKING`, raises one board item for the human with the PR and the finding: `board.py ask
  --cause info`, the finding in `--ask`, a fix story as the recommendation;
- adds the outcome once it is known (`worker_rights.py brake outcome --pr <N> --kind card --danger yes|no`):
  `yes` when the finding was real (a fix story or a held merge followed), `no` when not; for a
  `BLOCKING` after the human's answer, for a `PASS` at the merge.

## Lead checks around a worker

### Premise check

A count in the brief that comes from a heuristic script is written as an estimate (`~19, heuristic`)
for the worker to confirm before acting on it.

### Code graph in the brief

Where `.weside/config.json` → `tools.graphify` is true and the chunk changes a symbol called from
outside its own file, the brief names it: `graphify affected "<symbol>" --relation calls --depth 2`
before the edit. Everything else is `rg`; the brief needs no line for it.

### Watchdog

For a worker expected to run longer than ~30 min: `${CLAUDE_PLUGIN_ROOT}/scripts/watch-worker.sh <wt> <name>`
as a background command (a Bash call of its own with `run_in_background: true`, never `&` or
`disown`). It exits on what nobody else reports (a 25-min stall, the worktree gone, the session
ended) and on its 25-min lifetime cap; a commit is a line it prints and watches on (`--on-commit`
ends on it); its header lists the lines and exit codes. When the worker's report arrives or the
worker is stopped, `TaskStop` its watchdog by task id in the same turn, never by a `pkill` pattern.
A short worker needs none: the report gates send it back to work.

A worker whose next step waits on another PR's merge pushes, reports what is left and ends; its
starter resumes it on that merge. Waiting, it holds a slot and polls until its time limit.

An `exited:` line naming `auth` restarts the worker at once with the resume command it names (after
`usage-limit`: at the reset), one line to the coordinator; a worker that died stays a row in
`claude agents`, so only its living pid counts as alive. `we-worker status` lists window workers too.
A count you pass on (jobs done of N) comes from `gh run view <id> --json jobs` as you send it, not
from summed worker reports. A stall gets evidence (`git log -3`, `git status`, the agent's state)
before any word about it.

### After each lane merge

In the integration tree: the repo's type-checker on the files the merge changed (`git -C <int> diff --name-only HEAD^1 HEAD`) and the tests that import them (`rg -l` over
the changed module names in the test trees). Red → fix before the next merge.

## Report

A subagent's final message is the report, and the Agent result delivers it; a process worker sends
it as one `SendMessage` to its `Lead:` (§ Worker launch backend). Fields:

```
branch: <name> · worktree: <path> · commits: <n> · pushed: yes|no
gates: <command> @ <short HEAD sha> → <its result line> | skipped(<why>) …   (the receipt the Lead reads instead of re-running)
ACs: <AC id> → <test name or file:line> …   (one line per AC the chunk claims)
review: code-review high <found> found · <fixed> fixed · <skipped> skipped (<why>)   (only when the finish sequence ran one)
finish sequence: done|not ordered · verification: <oracle + receipt location>|not ordered
retired: <old test> → <new-seam test> …   (refactor chunks; none|<reason> when nothing retired)
tests: +<N> new functions, +<C> cases, extended: <k>, slowest new: <test (s)>|n/a   (N and C from `scripts/test-delta.py <base>`; k = existing tests that took the assertion; references/test-economy.md)
overrides: … · skipped: … · questions: … · blockers: none|<reason>
```
