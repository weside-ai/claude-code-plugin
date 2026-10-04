---
name: worker-dispatch
description: How the Lead picks and dispatches a dev worker, the dev-only worker contract, the finish sequence before the first push, and the report. Shared by /we:orchestrate and /we:develop.
---

# Worker dispatch

## Contents

Choosing the worker · Dev-only worker contract · Finish sequence · Lead checks around a worker
(premise check, watchdog, lane merge) · Report.

The Lead (`/we:orchestrate`) dispatches; the worker (`/we:develop`) obeys the contract below. A
worker cannot rely on reading this file: the Lead's brief carries every rule the chunk needs.

## Choosing the worker

- Dispatch shape: `Agent(name=…, subagent_type="we:dev-medium" | "we:dev-high", isolation="worktree", description=…, prompt=<brief>)`.
  Never `general-purpose`: a subagent inherits the session effort, and only the agent file's
  `effort:` overrides it (red arm, 27.09.2026).
- Default `we:dev-medium`. `we:dev-high` for: a promise that must hold across several code paths
  ("always", "exactly once"); transactions, money or idempotency; auth or tenant isolation; a fix
  routing around a fragile path; the second attempt after a failed worker; plan-writing (Foxy
  27.09.2026). The Lead writes the reason as one line in `description`; no reason, no `dev-high`
  (01.10.2026: 9 of 121 dispatches named none). A clearly bounded single fix stays medium: the bench
  (n = 27) found no difference there, and high costs about a third more time and money.
- Implementation never runs on Sonnet (Foxy 27.09.2026). `model: "haiku"` or `"sonnet"` only for a
  chunk the Lead names mechanical (a rename, a generated file, a gate run).
- Codex is not a dispatch backend; it reviews advisory only (Foxy 30.09.2026).
- One implementer per phase group. Parallel workers saved no net time in 48 of 54 v6 runs, because
  waves ran in series and integration ate the gain; a lone worker then ran 93–317 min serially over
  phases with disjoint files (27.–30.09.2026). Run chunks in parallel when the plan's
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

## Dev-only worker contract

- The brief outranks every default in `/we:develop`. The worker names each override in its report.
- A brief never overrides a stop. The worker stops and reports `blocked` when the plan carries an
  unanswered `## Open Fork`, when a ticket comment changes the scope after the plan, when the same
  gate fails three times, or when the work needs a product decision, a money-path redesign or a
  foreign subsystem's redesign.
- The worker never opens a PR, runs or waits for CI, moves or creates a ticket, merges a branch, or
  edits files outside its chunk. It pushes only when the brief says `Push: yes`, or when the Lead
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

1. The deterministic gates over the whole branch: the pre-push hooks and the affected tests by name.
2. Only when the diff touches money, auth, tenant isolation or a migration: the contract's
   `code-review` at `high` through the Skill tool, never as a slash command written into a subagent
   prompt (not proven to run the skill, probe 27.09.2026). No other LLM review.
3. Verification against a running instance when the brief orders it, per `.weside/verify.md`: DEV
   only (staging is a question to the human). The receipt goes into the plan's `## Verification`
   with the four literal labels `**Oracle:**`, `**Seed:**`, `**Asserted:**`, `**Not proven:**`.
   `not-applicable` is a valid receipt only with its reason.
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

### Watchdog

Armed at dispatch, one per worker: a background command (`run_in_background`) that exits on
the first event, so the Lead reports and re-arms; 25 min stays under its default 30-min timeout:

```bash
H0=$(git -C <wt> rev-parse HEAD); S0=$(git -C <wt> status --porcelain | md5sum); T=$(date +%s)
while :; do sleep 60; H=$(git -C <wt> rev-parse HEAD); S=$(git -C <wt> status --porcelain | md5sum)
  [ "$H" != "$H0" ] && { git -C <wt> log --oneline -1; exit 0; }
  [ "$S" != "$S0" ] && { S0=$S; T=$(date +%s); }
  [ $(( $(date +%s) - T )) -gt 1500 ] && { echo "STALL 25 min: <name>"; exit 0; }; done
```

A commit becomes one status line to the human (phase done). A stall gets evidence (`git log -3`,
`git status`, the agent's state) before any word about it. Three runs with it had 0 idle nudges
by the human (#4308, #4326, #4328); without it a worker sat idle 7 h 47 min (#4299).

### After each lane merge

In the integration tree: the repo's type-checker on the files the merge changed (`git -C <int> diff --name-only HEAD^1 HEAD`) and the tests that import them (`rg -l` over
the changed module names in the test trees). Red → fix before the next merge. Skipping it cost 14
red tests at the finisher on #4310.

## Report

The worker's final message is the report; the Agent result delivers it to the Lead. Fields:

```
branch: <name> · worktree: <path> · commits: <n> · pushed: yes|no
gates: <gate> ✓|✗|skipped(<why>) …
ACs: <AC id> → <test name or file:line> …   (one line per AC the chunk claims)
review: code-review high <found> found · <fixed> fixed · <skipped> skipped (<why>) | none (not critical)
finish sequence: done|not ordered · verification: <oracle + receipt location>|not ordered
overrides: … · skipped: … · questions: … · blockers: none|<reason>
```
