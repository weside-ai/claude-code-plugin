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
"worktree"`) for what has one; push once, open one PR, watch CI with `Monitor`. You never merge by hand; arming auto-merge per
§ Close the run is the human's standing permission (Foxy 30.09.2026). You stop only for the
Decision Queue or a protected action (release, staging deploy, anything destructive). Every other
status note goes into the same message as your next tool call. While a worker, refiner or `Monitor`
runs, a question to the human goes through `AskUserQuestion`, recommendation first and marked
"(Recommended)": plain text scrolls away under notifications (Foxy 30.09.2026). An
`idle_notification` that repeats a delivered report gets no message; only a new fact does.

Broad reading (a sweep over many files, "where is X") goes to `Agent(subagent_type="we:explore-medium")`, never the
built-in `Explore`: it inherits your session effort. Dispatch facts, the worker contract and the finish sequence: `${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md`.
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
5. An epic plan with `## Orchestration contract` binds the run: its rebuild order, upkeep table,
   permissions and stops replace the defaults here. Ask only what it leaves open. A contract may
   add stops; it never arms auto-merge earlier than § Close the run.

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
two to four plans per batch at most. Whether to create a ticket or a story is never a queue item. A resume word ("weiter") answers the run, never an open
decision. A story with no answer yet is parked in the repo's backlog status. Plans that pass the
scan and are approved need no confirm: the invocation is the go.

## Refine lane

A refiner is `Agent(subagent_type="we:dev-high", isolation="worktree", name="refiner-<KEY>")`
whose brief begins: "Use the Skill tool with skill `we:refine` and args `<KEY>`" (a bare `/we:refine` in a subagent prompt is not proven to run the skill, probe 27.09.2026). Refiners may run in parallel (up to three); each writes one file. The
brief carries the context a human would give: epic frame (3–5 lines), the story's intent, scope
in/out, known constraints and seams, one to three architecture docs to read first, and "a design
fork you cannot settle → write `## Open Fork` and stop".

On return, run the DoR scan on the plan in the returned worktree, then one `we:explore-medium`
checks every code claim in the plan (file:line, "only caller", "no reader", each named lever)
against the code; a wrong claim goes back to the refiner. Pass → approval batch. Fail →
re-dispatch once naming the missing item, then Decision Queue. An approved plan is committed per
`${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` (copied out of the refiner's worktree, step 3; never the shared main checkout); then remove the
refiner's worktree (step 6) and move the ticket to the plan-approved status.

## Build

**Before every dispatch:** `git fetch origin`, re-read the plan (another session may have built it),
move the ticket to In Progress and verify, check the brief's premises (`worker-dispatch.md`
§ Premise check). Choose the effort per
`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md` § Choosing the worker. The plan's
`parallel_groups` are binding: dispatch each group in one message, or write the reason against it
into `description`.

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
Scratch: temp files only under <scratchpad>/<name>/, never in the scratchpad root.
Report: worker-dispatch.md § Report fields, as your final message; a skill's output is never it.
```

**While a worker runs:** arm the watchdog at dispatch (`worker-dispatch.md` § Watchdog); refine the
next story or draft the PR body; the Agent result brings the report. A result without the Report
fields is an early turn end: `SendMessage` the worker to continue at the step it stopped. A steer is `SendMessage(to=<name>)`; it is read
at the worker's next turn boundary (measured: not acted on after 140 s), so every steer names a file
to write, and you check that file before assuming it landed. A liveness question gets evidence
(`git -C <worktree> log --oneline -3`, `git status`), never a status roll-up. Never spawn a
replacement while the original may be alive: `TaskStop`, verify, then re-dispatch on `we:dev-high`.

**Parallel chunks** (per the plan's `parallel_groups` or § Choosing the worker): create the integration worktree
`git worktree add <repo>-<KEY>-integration -b <type>/<KEY>-<slug> origin/<default>`, dispatch
the wave in one message, and merge each returned branch with
`git -C <int> merge --no-ff <branch> -m "chore(<KEY>): integrate <branch>"`. A result without
commits is a lost dispatch: re-dispatch, never integrate an empty tree. After each merge run
`worker-dispatch.md` § After each lane merge; a contract change breaks a sibling no chunk gate covered. Conflicts resolve by the plan's Constraints; a non-trivial one goes to the human.
Then one `we:dev-medium` finisher with `cwd=<int>` runs the finish sequence.

## Push, PR, CI

1. Read the report. Run the tests it names yourself in the worker's worktree. Check the AC →
   evidence lines and the rows of `.weside/dod.md` against the named files and tests. Then dispatch
   the independent review (`worker-dispatch.md` § Independent review). A missing AC, a DoD `Fail`,
   a red gate or a review finding goes back to the same worker by `SendMessage`.
2. A migration gets `upgrade → downgrade → upgrade` on a real database. Run
   `git -C <wt> merge origin/<default>`, then push once from the PR branch's worktree
   (`git -C <wt> push -u origin <branch>`); the pre-push hooks run once over the whole diff.
   Point the statusline at it: `~/.claude/we-focus/$CLAUDE_CODE_SESSION_ID.json` with
   `{"dir":"<wt>","branch":"<branch>","pr":<n>}` (add `pr` after step 3).
3. `gh pr create --body-file <file>`: ticket link, AC → evidence, the `## Verification` receipt
   from the plan, and one line naming money, auth or tenant work when the diff has it. Move every
   landed story to In Review and verify.
4. Arm `Monitor` on `gh pr checks <PR> --json name,bucket`, emitting only a failed or cancelled
   check and the final state, never each green check, and exiting when none is pending. Meanwhile refine or prepare the next story.
5. Once no check is pending, green or red, run `/we:ci-review <PR>` without asking: open bot threads
   and review findings remain on a green run. Never from the shared main checkout:
   `EnterWorktree(path=<wt>)` first, or a `we:dev-medium` with `cwd=<wt>` runs it. Its round cap
   (three) and terminal states end the run.

## Close the run

- **Auto-merge is the default** (Foxy 30.09.2026): when `/we:ci-review` ends green, with every Codex
  finding read, run `gh pr merge <PR> --auto --merge` (`--squash`/`--rebase` when `.weside/orchestrate.md`
  names it; gh refuses `--auto` without a method outside a terminal). Not before: Codex is no
  required check, and an early arm merges its finding unread. No auto-merge when the invocation
  says `--user-merge`, the diff touches a money path or a destructive migration, it adds a
  migration while another open PR adds one too, a follow-up still runs on the branch, or a
  question to the human is open; the closing message then says `user merge: <reason>`. A fix round
  on an armed PR starts with `gh pr merge <PR> --disable-auto`.
- **Auto retro** when the run was not smooth: a worker failed, was stopped or re-dispatched; a dispatch came back
  empty; `/we:ci-review` needed two rounds or more; the user corrected an assumption or an action; a report
  said green and was not; or a Decision-Queue item was answered by a fact the instruction files should hold.
  Then dispatch it per `${CLAUDE_PLUGIN_ROOT}/skills/retro/SKILL.md` § Auto mode; it is the one agent
  that keeps running after the run closes.
  A smooth run gets none; the closing message says `retro: <reason> | skipped (smooth)`.
- The closing message starts with `PR #<n> · <branch> · <worktree> · CI <state> · auto-merge|user merge`,
  then at most three items someone owes. For a user merge it is the `/we:standup` output. While a
  follow-up runs on the branch, every message says "do not merge yet". A finding on the run's own diff (a Codex finding, a type error, a fallback) is
  decided per finish-first and reported, never asked (final sim 28.09.2026). Knowledge goes into the
  plan. No ticket during a run, and no question whether to create one: name the follow-ups (Foxy 25.09.2026).
- Stop leftover agents with `TaskStop`, except the auto retro. Keep the PR branch's worktree until the merge. Release
  single-owner ports per `worker-dispatch.md` § Finish sequence.
- An epic run: after every merged story run the epic upkeep (`/we:epic` update: mirror, Updates Log,
  Learnings forward) and commit it before the next story starts. After a compact, rebuild state
  from the epic, git, the PRs and the tickets, never from the summary. The epic on the default
  branch is the backup; no extra documentation pass (Foxy 01.10.2026).
- After the merge, `/we:merged` closes out: it finds the run's branches and worktrees by `<KEY>` in
  git and the PR by number.

## `--solo`

For one straight-line phase, a config change, a one-function fix. `EnterWorktree(name=…)`, rename
the branch (`git branch -m <type>/<KEY>-<slug>`), run the bootstrap explicitly, implement the phases
in order with the local gates of the worker contract, run the finish sequence yourself, then
§ Push, PR, CI. Stop only for a gap the code cannot close, three failures in one gate, or
anything destructive.
