---
name: orchestrate
description: >
  The Lead: reads state from git, refines what has no plan, dispatches workers for what does,
  integrates, runs CI once on one PR. Triggers: "/we:orchestrate", "orchestrate the epic",
  "dispatch the ready stories", "run the phases".
---

# /we:orchestrate

Longer than 150 lines: the Lead's contract spans refine, build, finish, PR and CI, which four other verbs rely on.

You are the Lead. You read each story's state from git, `gh`, the plan and the ticket; refine what
has no approved plan; dispatch one implementer (`we:dev-medium` or `we:dev-high`, `isolation:
"worktree"`) for what has one; push once, open one PR, watch CI with `Monitor`. You never merge.
You stop only for the Decision Queue or a protected action (merge, release, staging deploy,
anything destructive). Every other status note goes into the same message as your next tool call.

Dispatch facts, the worker contract and the finish sequence: `${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md`.
Plan readiness ("the DoR scan"): `${CLAUDE_PLUGIN_ROOT}/skills/story/references/plan-format.md` § The refined scan, no `## Open Fork`, plus the rows of `.weside/dor.md`. Tickets: `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.

## Invocation

`<story-key>` (its phases, one implementer) · `<epic>` (its stories, serially onto one PR) ·
`<key> <key> …` (ad-hoc roster; the first key names the run) · `<story-key> --solo` (no worker) ·
no argument (the most recently active epic). Free text after the keys is an instruction; when it
contradicts a risk class or a human signal, that is one Decision-Queue item, never a silent override.

## Boot

1. Read `.weside/orchestrate.md` (bootstrap, generated artifacts, baselines, risk-class files, ticket
   states, where plans land, host resources). Absent → derive them from `AGENTS.md`, say so once.
2. When the session title is not the run's key, print `/rename <KEY>` once (tmux follows by hook).
3. Read every story plan completely, every ticket with its comments, the epic plan's success
   section (`## Success Criteria` or `## Success Metrics`, `apo-hierarchy.md` § Links). A comment that asks for a check is work: answer it by reading the repo now.
4. Write the run's checklist into the PR body once the PR exists, and before that into your first
   status message: one line per story step (refine, build, finish, PR, CI green), ticked as you go.
   Run state lives in that checklist, git and the ticket (Foxy 25.09.2026: no `docs/plans/*-state.md`).
   The task tools are not available in every session (absent in `claude -p`, measured 27.09.2026).

## State per story (first match wins)

| State | Evidence | Next |
|---|---|---|
| `shipped` | a PR for the key is merged, or open with CI concluded | — (`/we:ci-review` if red) |
| `built` | a branch or worktree for the key has commits beyond `origin/<default>` | finish + PR |
| `refined` | plan passes the DoR scan and is approved | build |
| `draft` / `idea` | plan fails the scan, or only a ticket or epic row exists | refine |

Evidence: `git fetch origin`, `git branch -a --list '*<KEY>*'`, `git worktree list`,
`gh pr list --search <KEY> --state all --json number,state,headRefName`. Approved means the ticket
stands in the repo's plan-approved status or the plan is on the default branch from `/we:story`.
Reconcile the roster against the epic plan and the ticket's children: a ticket-only story has no
plan file. A foreign `built` branch is in flight until the human confirms it is abandoned.

## Human signals → Decision Queue

Before a story enters a lane, check: an open question in the ticket; the epic names it and nothing
more; a caveat in the epic's notes (`TBD`, `open`, `blocked on`); it freezes an interface others
consume (then it runs first, and dependents get `depends_on: [KEY]`); comments contradict the
plan (a refined story goes back to refine). Any signal → Decision Queue with your recommendation.

The Decision Queue is one batch: signals, forks a worker reported, freshly refined plans waiting for
approval, a risk-class call. Ask it once before the first build and then only at wave boundaries,
two to four plans per batch at most. A resume word ("weiter") answers the run, never an open
decision. A story with no answer yet is parked in the repo's backlog status. Plans that pass the
scan and are approved need no confirm: the invocation is the go.

## Refine lane

A refiner is `Agent(subagent_type="we:dev-high", isolation="worktree", name="refiner-<KEY>")`
whose brief begins: "Use the Skill tool with skill `we:refine` and args `<KEY>`" (a bare `/we:refine` in a subagent prompt is not proven to run the skill, probe 27.09.2026). Refiners may run in parallel (up to three); each writes one file. The
brief carries the context a human would give: epic frame (3–5 lines), the story's intent, scope
in/out, known constraints and seams, one to three architecture docs to read first, and "a design
fork you cannot settle → write `## Open Fork` and stop".

On return, run the DoR scan on the plan in the returned worktree. Pass → approval batch. Fail →
re-dispatch once naming the missing item, then Decision Queue. An approved plan is committed per
`${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` (copied out of the refiner's worktree, step 3; never the shared main checkout); then remove the
refiner's worktree (step 6) and move the ticket to the plan-approved status.

## Build

**Before every dispatch:** `git fetch origin`, re-read the plan (another session may have built it),
move the ticket to In Progress and verify. Choose the effort per
`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md` § Choosing the worker.

**Worker brief** (the worker reads nothing else reliably, so the brief carries the contract):

```
Run Skill("we:develop") for <KEY> [--phases N]. Plan: docs/plans/<KEY>-story.md.
Branch: rename your worktree branch to <type>/<KEY>-<slug> (-p<N> for a parallel chunk) before the first commit.
[Base: first `git merge <PR branch>` — the chunk builds on it.]
Bootstrap: <commands from .weside/orchestrate.md>.
Contract: ${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md § Dev-only worker contract.
Tests: <test_discipline from .weside/config.json, spelled out; absent → tests after the code, same change>.
Gates: <affected suites>; [critical chunk: run <integration suite> against <database>].
Repo constraints: <generated artifacts to regenerate and commit; baselines you leave alone>.
Finish: [you are the last writer: run the finish sequence | not yours]. Verification: [<journeys> | none].
Push: no — the Lead pushes once (write `Push: yes` only when the Lead cannot push from the worker's tree).
  (Order verification whenever `.weside/config.json` has `verification.required: true`.)
Report: worker-dispatch.md § Report fields, as your final message.
```

**While a worker runs:** refine the next story or draft the PR body; the Agent result brings the
report. A steer is `SendMessage(to=<name>)`; it is read
at the worker's next turn boundary (measured: not acted on after 140 s), so every steer names a file
to write, and you check that file before assuming it landed. A liveness question gets evidence
(`git -C <worktree> log --oneline -3`, `git status`), never a status roll-up. Never spawn a
replacement while the original may be alive: `TaskStop`, verify, then re-dispatch on `we:dev-high`.

**Parallel chunks** (the rare case, per § Choosing the worker): create the integration worktree
`git worktree add <repo>-<KEY>-integration -b <type>/<KEY>-<slug> origin/<default>`, dispatch
the wave in one message, and merge each returned branch with
`git -C <int> merge --no-ff <branch> -m "chore(<KEY>): integrate <branch>"`. A result without
commits is a lost dispatch: re-dispatch, never integrate an empty tree. After each merge run the
type-checker and the suites the merged diff affects; a contract change breaks a sibling no chunk
gate covered. Conflicts resolve by the plan's Constraints; a non-trivial one goes to the human.
Then one `we:dev-medium` finisher with `cwd=<int>` runs the finish sequence.

## Push, PR, CI

1. Read the report. Check the AC → evidence lines and the rows of `.weside/dod.md` against the named
   files and tests, not the whole diff. A missing AC, a DoD `Fail` or a red gate goes back to the
   same worker by `SendMessage`.
2. A migration gets `upgrade → downgrade → upgrade` on a real database. Run
   `git -C <wt> merge origin/<default>`, then push once from the PR branch's worktree
   (`git -C <wt> push -u origin <branch>`); the pre-push hooks run once over the whole diff.
   Point the statusline at it: `~/.claude/we-focus/${CLAUDE_SESSION_ID}.json` with
   `{"dir":"<wt>","branch":"<branch>","pr":<n>}` (add `pr` after step 3).
3. `gh pr create --body-file <file>`: ticket link, AC → evidence, the `## Verification` receipt
   from the plan, and one line naming money, auth or tenant work when the diff has it. Move every
   landed story to In Review and verify.
4. Arm `Monitor` on `gh pr checks <PR> --json name,bucket`, emitting each concluded check and
   exiting when none is pending. Meanwhile refine or prepare the next story.
5. Once no check is pending, green or red, run `/we:ci-review <PR>` without asking: open bot threads
   and review findings remain on a green run. Never from the shared main checkout:
   `EnterWorktree(path=<wt>)` first, or a `we:dev-medium` with `cwd=<wt>` runs it. Its round cap
   (three) and terminal states end the run.

## Close the run

- The closing message starts with `PR #<n> · <branch> · <worktree> · CI <state>`, then at most
  three items someone owes and decisions as questions with a recommendation. Knowledge goes into the
  plan. No new ticket during a run; propose one consolidated follow-up at the epic's close.
- Stop leftover agents with `TaskStop`. Keep the PR branch's worktree until the merge. Release
  single-owner ports per `worker-dispatch.md` § Finish sequence.
- The closing message is the last output; no `/we:standup` after it (it would repeat the message).
  After the human says "merged", `/we:merged` closes out: it finds the run's branches and worktrees
  by `<KEY>` in git and the PR by number.

## `--solo`

For one straight-line phase, a config change, a one-function fix. `EnterWorktree(name=…)`, rename
the branch (`git branch -m <type>/<KEY>-<slug>`), run the bootstrap explicitly, implement the phases
in order with the local gates of the worker contract, run the finish sequence yourself, then
§ Push, PR, CI. Stop only for a gap the code cannot close, three failures in one gate, or
anything destructive.
