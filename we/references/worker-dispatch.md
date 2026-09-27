---
name: worker-dispatch
description: How the Lead picks and dispatches a dev worker, the dev-only worker contract, the finish sequence before the first push, and the report. Shared by /we:orchestrate and /we:develop.
---

# Worker dispatch

The Lead (`/we:orchestrate`) dispatches; the worker (`/we:develop`) obeys the contract below. A
worker cannot rely on reading this file: the Lead's brief carries every rule the chunk needs.

## Choosing the worker

- Dispatch shape: `Agent(name=…, subagent_type="we:dev-medium" | "we:dev-high", isolation="worktree", description=…, prompt=<brief>)`.
  Never `general-purpose`: a subagent inherits the session effort, and only the agent file's
  `effort:` overrides it (red arm, 27.09.2026).
- Default `we:dev-medium`. `we:dev-high` for: a promise that must hold across several code paths
  ("always", "exactly once"); transactions, money or idempotency; a fix routing around a fragile
  path; the second attempt after a failed worker; plan-writing (Foxy 27.09.2026). The Lead writes
  the reason as one line in `description`. A clearly bounded single fix stays medium: the bench
  (n = 27) found no difference there, and high costs about a third more time and money.
- Implementation never runs on Sonnet (Foxy 27.09.2026). `model: "haiku"` or `"sonnet"` only for a
  chunk the Lead names mechanical (a rename, a generated file, a gate run).
- Codex is not a dispatch backend: its subscription ends by 11.10.2026 and it reviews only
  advisory (Foxy 27.09.2026).
- One implementer per story is the normal case. Parallel workers saved no net time in 48 of 54
  measured runs, because waves ran in series and integration ate the gain. Run two in parallel
  only when the union of their plan `**Files:**` lists does not intersect and the contract between
  them already exists on the base branch. Migrations, lockfiles, generated artifacts
  (`openapi.json`, typed clients) and gate baselines always serialize.

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
  edits files outside its chunk. It pushes only when the brief says so.
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

## Finish sequence (the last writer, before the first push)

The session or worker that writes last on the PR branch runs this once over
`git diff origin/<default-branch>...HEAD`, committing after each step:

Invoke each through the Skill tool (`skill: "code-review"`, `args: "medium"`); a slash command
written into a subagent prompt is not proven to run the skill (probe 27.09.2026).

1. `code-review` at `medium`, then fix what it finds.
2. `simplify`.
3. `security-review` in addition when the diff touches money, auth or tenant isolation.
4. Verification against a running instance when the brief orders it, per `.weside/verify.md`: DEV
   only (staging is a question to the human). The receipt goes into the plan's `## Verification`
   with the four literal labels `**Oracle:**`, `**Seed:**`, `**Asserted:**`, `**Not proven:**`.
   `not-applicable` is a valid receipt only with its reason.
5. The plan rewritten to what was actually built (`skills/story/references/plan-format.md` § Lifecycle).
6. The affected gates again, because steps 1–3 moved code.

Before starting a server, check who owns the single-owner ports (`ss -ltnp`, then
`ls -l /proc/<pid>/cwd`): `(deleted)` is an orphan and yours to clear; a live cwd in your worktree
is yours; a live cwd in another worktree belongs to another session, and you ask instead of
killing. PPID 1 is normal for a detached dev server and proves nothing. Stop your server by PID,
children included, the moment verification ends.

## Report

The worker's final message is the report; the Agent result delivers it to the Lead. Fields:

```
branch: <name> · worktree: <path> · commits: <n> · pushed: yes|no
gates: <gate> ✓|✗|skipped(<why>) …
ACs: <AC id> → <test name or file:line> …   (one line per AC the chunk claims)
finish sequence: done|not ordered · verification: <oracle + receipt location>|not ordered
overrides: … · skipped: … · questions: … · blockers: none|<reason>
```
