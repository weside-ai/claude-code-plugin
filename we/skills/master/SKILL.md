---
name: master
description: >
  The epic's master: pulls its Selected stories, starts a refiner worker where a plan is missing and
  a build worker where one exists, one PR per story and repo. Triggers: "/we:master", "master the epic",
  "dispatch the ready stories", "run the phases".
---

# /we:master

Longer than 150 lines: the Lead's contract spans refine, build, finish, PR and CI, which four other verbs rely on.

You are the Lead, the epic's master (L0 §Sessions). You read each story's state from git, `gh`, the plan and the ticket; start a
refiner worker for a story without a plan; start one build worker (`we:dev-medium` or `we:dev-high`) for a story with
one, through `agents.worker_launch` as a session of its own in a repo with a crew (`worker-dispatch.md`
§ Worker launch backend). You never build in your own session (one exception: a CI fix of ≤ 5 lines without user-visible text) and never
through a build subagent: a subagent reads and reviews, never builds. User-visible text never comes from you: its
owner writes or approves it before a worker builds it. Each story is one PR per repo, in its plan's order (L0 §Units): push once per story, open its PR, watch CI with `scripts/watch-pr-checks.sh`. You never merge by hand; arming auto-merge per
§ Close the run is the human's standing permission (owner 30.09.2026). You stop only for a protected
action (release, a staging deploy the epic's Orchestration contract does not grant, anything destructive); an open question parks only the chunk it blocks. Every other
status note goes into the same message as your next tool call. A question for the human goes, in a
repo with a crew, as one question line to the coordinator (L0 §Talking and the board); without a crew
as plain text at the end of your message, your recommendation last.
Phrase it per `${CLAUDE_PLUGIN_ROOT}/skills/grill/SKILL.md` § Discipline. An
`idle_notification` that repeats a delivered report gets no message; only a new fact does.

Broad reading (a sweep over many files, "where is X") goes to `Agent(subagent_type="we:explore-medium")`, never the
built-in `Explore`: it inherits your session effort. Dispatch facts, the worker contract and the finish sequence: `${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md`.
Plan readiness ("the DoR scan"): `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ready_gate.py story <plan>` exits 0 (`${CLAUDE_PLUGIN_ROOT}/references/story-plan.md` § Readiness), plus the rows of `.weside/dor.md`. Tickets: `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.

## Invocation

`<story-key>` (its phases, one implementer) · `<epic>` (its Selected stories, pulled one at a time,
each its own PR) · `<key> <key> …` (ad-hoc roster; the first key names the run) · no argument (the
most recently active epic). Free text after the keys is an instruction; when it contradicts a risk
class or a human signal, that is one question line to its owner, never a silent override.

## Boot

1. Read `.weside/orchestrate.md` (bootstrap, generated artifacts, baselines, risk-class files, ticket
   states, where plans land, host resources, post-merge command). Absent → derive them from `AGENTS.md`, say so once.
   A crew whose launcher is not on this host: `worker-dispatch.md` § Worker launch backend (fallback or stop).
2. When the session title is not the run's key, print `/rename <KEY>` once (tmux follows by hook).
   A master named by the crew (L0 §Sessions) keeps its name; a bound companion session skips it (`references/companion-session.md` § Name and binding).
3. Read every story plan completely, every ticket with its comments, the epic plan's success
   section (`## Success Criteria` or `## Success Metrics`, `${CLAUDE_PLUGIN_ROOT}/references/epic-plan.md` § Links). A comment that asks for a check is work: answer it by reading the repo now.
4. Write the run's checklist into the PR body once the PR exists, and before that into your first
   status message: one line per story step (refine, build, finish, PR, CI green), ticked as you go.
   Run state lives in that checklist, git and the ticket (owner 25.09.2026: no `docs/plans/*-state.md`).
   The task tools are not available in every session (absent in `claude -p`, measured 27.09.2026).
5. An epic plan with `## Orchestration contract` binds the run: its rebuild order, upkeep table,
   permissions and stops replace the defaults here. Ask only what it leaves open. A contract may
   add stops; it never arms auto-merge earlier than § Close the run.

## State per story (first match wins)

| State | Evidence | Next |
|---|---|---|
| `shipped` | a PR for the key is merged, or open with CI concluded | — (`/we:ci-review` if red) |
| `built` | a branch or worktree for the key has commits beyond `origin/<default>` | finish + PR |
| `refined` | plan on the default branch passes the Ready gate (Selected) | build |
| `draft` / `idea` | plan fails the scan, or only a ticket or epic row exists | refine |

Evidence: `git fetch origin`, `git branch -a --list '*<KEY>*'`, `git worktree list`,
`gh pr list --search <KEY> --state all --json number,state,headRefName`. A refined plan enters
Selected by the Ready gate and the lens panel, never by a person approving the story:
approval is per epic (L0 §Units). The one exception is the master card's unconfirmed-fence rule.
Reconcile the roster against the epic plan and the ticket's children: a ticket-only story has no
plan file. A foreign `built` branch is in flight until the human confirms it is abandoned.

## Human signals → questions and decision stories

Before a story enters a lane, check: an open question in the ticket; the epic names it and nothing
more; a caveat in the epic's notes (`TBD`, `open`, `blocked on`); it freezes an interface others
consume (then it runs first, and dependents get `depends_on: [KEY]`); comments contradict the
plan (a refined story goes back to refine). Any signal → one question line to its owner with your
recommendation; a product question mid-run becomes one decision story (L0 §Units).

Questions go to their owner directly (L0 §Talking and the board): signals, forks a worker reported, a
risk-class call. The WHAT goes to the Product Owner, the HOW to the epic owner (label `owner-<slug>`,
else the component owner), what only the human decides as one question line to the coordinator. A
question never stops independent work: first dispatch everything that does not depend on an answer,
then ask early, and park only the chunk an answer blocks. An important question is
still asked, never skipped silently. Before a known quota end, tell each worker to commit its phase
and push it to `wip/<KEY>-<slug>`. Whether to create a ticket or a story is never a queue item. A resume word ("weiter") answers the run, never an open
decision. A story with no answer yet is parked in the repo's backlog status. A Selected plan needs
no confirm: the invocation is the go.

## Refine lane

A refiner is a `we:dev-high` worker `refiner-<KEY>` that you start (L0 §Lifecycle: the epic's
master starts it; the owner judges, never starts), whose brief begins: "Use the Skill tool with skill `we:plan-story` and args `<KEY>`" (a bare `/we:plan-story` in a subagent prompt is not proven to run the skill, probe 27.09.2026). Refiners may run in parallel (up to three); each writes its plan and, for `receipt` ACs, the staging-check file the plan's `**Staging checks:**` line names. The
brief carries the context a human would give: epic frame (3–5 lines), the story's intent, scope
in/out, known constraints and seams, one to three architecture docs to read first, and "a design
fork you cannot settle → write `## Open Fork` and stop".

On return, run the DoR scan on the plan in the returned worktree, then one `we:explore-medium`
checks every code claim in the plan (file:line, "only caller", "no reader", each named lever)
against the code; a wrong claim goes back to the refiner. Pass → set `status: approved` in the plan's
frontmatter, then commit it per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` (plan and staging-check
file copied out of the refiner's worktree, step 3, and committed together, step 4; never the shared main
checkout). Fail → re-dispatch once naming the missing item, then one question line to the epic owner. Then remove the
refiner's worktree (step 6). On the default branch (its docs PR merged) and green under the Ready gate the story is
Selected; move its ticket per `ticketing.md`, which names the mover for every state.

## Build

**Fill the slots:** each time a PR merges or a worker ends, list every story whose dependency is now met (the
merged artifact its plan names, not the whole story) and every story without a plan, and dispatch until the worker
limit (L0 §Sessions) is reached. Two stories whose plans touch the same files never run in parallel: the second
waits for the first one's merge.

**Before every dispatch:** `git fetch origin`, re-read the plan (another session may have built it),
pull the story: move its ticket Selected → In Progress per `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`
(L0 §Lifecycle; `board.py move`), check the brief's premises (`worker-dispatch.md`
§ Premise check) and decide its code-graph line (§ Code graph in the brief). Choose the effort per
`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md` § Choosing the worker. The plan's
`parallel_groups` are binding: dispatch each group in one message, or write the reason against it
into `description`.

**Worker brief** (the worker reads nothing else reliably, so the brief carries the contract):

```
Run Skill("we:develop") for <KEY> [--phases N]. Plan: docs/plans/<KEY>-story.md.
Branch: <type>/<KEY>-<slug> (-p<N> for a parallel chunk); rename `worktree-…` to it before the first commit.
[Base: first `git merge <PR branch>` — the chunk builds on it.]
Bootstrap: <commands from .weside/orchestrate.md>.
Contract: ${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md § Dev-only worker contract.
Tests: <test_discipline from .weside/config.json, spelled out; absent → tests after the code, same change>.
Gates: <affected suites>; [critical chunk: run <integration suite> against <database>].
[Code graph: graphify affected "<symbol>" … | graph query "<question>" | not needed (<reason>)]   (only when tools.graphify is true)
Repo constraints: <generated artifacts to regenerate and commit; baselines you leave alone>.
[Must-dos carried from the Ready panel: <each `carried` item of the story's last `selected` row in board-transitions.jsonl, as `<lens>: <claim> (<where>)`>]
Finish: [you are the last writer: run the finish sequence | not yours]. Verification: [<journeys> | none].
Push: no — the Lead pushes once (write `Push: yes` only when the Lead cannot push from the worker's tree).
  (Order verification whenever `.weside/config.json` has `verification.required: true`.)
Scratch: temp files only under <scratchpad>/<name>/, never in the scratchpad root.
Report: worker-dispatch.md § Report fields, as your final message or to your `Lead:`; a skill's output is never it.
  Before it, message the Lead only for a terminal fact: pushed SHA, green, cap, blocked, a question.
```

**While a worker runs:** arm the watchdog at dispatch (`worker-dispatch.md` § Watchdog), never a
`Monitor` on worker progress: the report arrives as a notification. Refine the next story or draft
the PR body. The plugin's report gates
send a worker that stopped before its report back to work; a result still without the Report fields
(the hook let it pass, or hit its block cap) gets `SendMessage` to continue at the step it stopped. A steer is `SendMessage(to=<name>)`; it is read
at the worker's next turn boundary (measured: not acted on after 140 s), so every steer names a file
to write, and you check that file before assuming it landed. A liveness question gets evidence
(`git -C <worktree> log --oneline -3`, `git status`), never a status roll-up. Never spawn a
replacement while the original may be alive: stop it, verify, then re-dispatch on `we:dev-high`.

**Parallel chunks** (per the plan's `parallel_groups` or § Choosing the worker): create the integration worktree
`git worktree add <repo>-<KEY>-integration -b <type>/<KEY>-<slug> origin/<default>`, dispatch
the wave in one message, and merge each branch as it returns, not after the wave (chunks sat 20–35
min unmerged, 17.10.2026): `git -C <int> merge --no-ff <branch> -m "chore(<KEY>): integrate <branch>"`.
A serial successor is dispatched on its predecessor's head the moment that one reports. A result without
commits is a lost dispatch: re-dispatch, never integrate an empty tree. After each merge run
`worker-dispatch.md` § After each lane merge; a contract change breaks a sibling no chunk gate covered. Conflicts resolve by the plan's Constraints; a non-trivial one goes to the human.
Then one `we:dev-medium` finisher in `<int>` runs the finish sequence.

## Push, PR, CI

1. Read the report. Re-run a test it names, in the worker's worktree, only when its `gates:` line
   lacks a receipt (the command, the HEAD it ran on, its result line), that HEAD is not the branch's HEAD, or you changed the tree after the report (a
   lane merge, your own fix); CI runs the suite again, and § After each lane merge covers integration.
   Check the AC → evidence lines and the rows of `.weside/dod.md` against the named files and tests. No local LLM
   review: CI runs the Claude and Codex reviews (`worker-dispatch.md` § Finish sequence). A missing
   AC, a DoD `Fail` or a red gate goes back to the same worker by `SendMessage`.
2. A migration gets `upgrade → downgrade → upgrade` on a real database. Run
   the conflict check of `/we:ci-review` § 3 in `<wt>` (merge `origin/<default>` only on a conflict), then push once from the PR branch's worktree
   (`git -C <wt> push -u origin <branch>`); the pre-push hooks run once over the whole diff.
   Point the statusline at it: `~/.claude/we-focus/$CLAUDE_CODE_SESSION_ID.json` with
   `{"dir":"<wt>","branch":"<branch>","pr":<n>}` (add `pr` after step 3).
3. A "push now" relay to a worker says "push; merge `origin/<default>` first only on a conflict". `gh pr create --body-file <file>`: ticket link, AC → evidence, the plan's `## Verification` block
   spliced in by `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pr-body-receipt.py <KEY> <body-in> <body-out>` (never retyped), the test line per `/we:pr` step 3, and one line naming money, auth or tenant work when the diff has it. `--draft` only per
   `/we:pr` step 4. The `receipt …` line comes only from that script (`/we:pr` step 3). Link the PR to the ticket and move
   no status: In Review is "PR merged and linked" (L0 §Lifecycle) and `/we:merged` sets it.
4. Run `${CLAUDE_PLUGIN_ROOT}/scripts/watch-pr-checks.sh <PR> --sha <pushed sha>` as a background command,
   with `--until-merged` once auto-merge is armed, and next to it one
   `${CLAUDE_PLUGIN_ROOT}/scripts/watch-pr-conflicts.sh <PR>…` over the run's open PRs. The headers list
   the exit codes. One checks watcher per PR: a worker running `/we:ci-review` on it watches until green
   (L0 §Sessions), then you arm it `--until-merged`. Meanwhile refine or prepare the next story.
5. You stay on an auto-merge PR until it is merged; the user never runs `/we:ci-review` or
   `/we:merged` by hand on it (owner 28.10.2026). On the watcher's exit, without asking:
   - red, or exit 6 (Codex WARNING/BLOCKING on the head; the watcher has disarmed auto-merge on it and on a red
     review check) → `/we:ci-review <PR>`, which re-arms when green. Never from the shared main checkout: `EnterWorktree(path=<wt>)` first,
     or a `we:dev-medium` worker in `<wt>` runs it. Green but not yet armed → the same, open threads and
     findings remain on a green run.
   - exit 7 (merged) → `/we:merged <PR>` yourself; exit 8 (closed) → report.
   - exit 3 (head moved) or 0 under `--until-merged` (conflict, behind, auto-merge off) → handle it,
     then re-arm on the new head.
   Bounds, no `/loop` or `/goal`: ci-review's three rounds; the watcher's 6-h lifetime (exit 9 →
   report); at most three re-arms per PR head; a repeat finding (ci-review § 4) stops and reports.
6. A conflict exit of `watch-pr-conflicts.sh` (or the `conflict_gate.py` Stop hook) goes back to the
   PR's worker (merge the default branch, after-merge check, push) without asking; re-arm the watch after the push.

## Close the run

- **Auto-merge is the default** (L0 §Risk tiers and who waits on whom): run `gh pr merge <PR> --auto --merge` right after
  `gh pr create` when the base branch requires the Codex check (`review.codex_check`, default
  `Codex Review`; GitHub then waits for Codex), else when `/we:ci-review` ends green with every Codex
  finding read (`--squash`/`--rebase` when `.weside/orchestrate.md`
  names it; gh refuses `--auto` without a method outside a terminal). A T2 diff arms after the lens
  panel's verdict. The hook `automerge_gate.py` refuses an early arm while that
  check is not required, and refuses any merge from a worker. The only merge brake is the **one-way
  class**, computed by the crew's `risk.command` on the diff (code that computes money, destructive migration,
  Terraform or secrets, the brake's core `brake-change`): no session merges or arms it. Run the
  T2 panel on it and post it (`/we:lens t2 <PR>`); where the repo runs a self-merge window
  (`${CLAUDE_PLUGIN_ROOT}/docs/board.md` § Self-merge window) it merges itself 2 h after that comment unless vetoed. The
  brake's core, and every one-way PR in a repo without the window, only the human merges, from a
  board item with the PR link, the class and the panel verdict (`board.py ask --cause merge-go --pr <url>
  --one-way <class>`); until the merge hook computes the
  class, run the command yourself before you arm. The closing message then says
  `user merge: one-way (<class>)`. A `T2` line 1 with a `trust-loosening:`, `money-path:` or
  `brake-review:` hit line (a card hit) is no merge brake: once the panel is green, start a security
  card worker on the head (`we-worker <KEY>-card --bg "/<security holder's skill> …"`, brief per
  `references/worker-dispatch.md` § Card worker) and arm after its `Overall: PASS` comment; a push
  needs a new verdict, and `automerge_gate.py` refuses the arm until one stands on the head. A draft reason (a follow-up still on the branch, an unmerged
  dependency) keeps the PR a draft per `/we:pr` step 4; it is no merge brake. Non-destructive migrations auto-merge serially (owner 03.10.2026): the
  second PR arms only after the first landed, merging `origin/<default>`, checking for one migration
  head, and pushing first. A fix round
  on an armed PR starts with `gh pr merge <PR> --disable-auto` and never drafts (`/we:ci-review` § 1).
- **Auto retro** only when you can name a concrete, new friction of the run that an instruction change
  would prevent (a wrong assumption the files should have held, a script that misled, a repeated user
  correction); round counts alone are no reason (owner 28.10.2026). Then dispatch it per
  `${CLAUDE_PLUGIN_ROOT}/skills/retro/SKILL.md` § Auto mode with that friction in the brief; it is the
  one agent that keeps running after the run closes. Otherwise skip it without asking; the closing
  message says `retro: <friction> | skipped (<reason>)`.
- The closing message starts with `PR #<n> · <branch> · <worktree> · CI <state> · auto-merge|user merge`,
  then at most three items someone owes. For a user merge it is the `/we:standup --branch` output. While a
  follow-up runs on the branch, every message says "do not merge yet". A finding on the run's own diff (a Codex finding, a type error, a fallback) is
  decided per finish-first and reported, never asked (final sim 28.09.2026), unless its fix replaces a design the
  plan fixed (another mechanism, a dropped AC, a changed interface): that goes back to the epic owner first. Knowledge goes into the
  plan. A product question mid-run becomes one decision story (L0 §Units); every other follow-up is named,
  never ticketed during the run (owner 25.09.2026).
- A repo that bumps its version per PR (its `AGENTS.md` says so): workers leave the version alone; you set it as
  the last commit before the arm, above `origin/<default>` and every armed open PR.
- Stop leftover workers, except the auto retro. Keep the PR branch's worktree until the merge. Release
  single-owner ports per `worker-dispatch.md` § Finish sequence.
- In a repo with a crew the Lead is an unnamed build master: product questions to the Product Owner,
  the HOW to the epic owner (else the component owner), each milestone (plan on main, PR opened or merged, a blocker) as one line
  to the coordinator, a question for the human as one question line through it (L0 §Talking and the board). A Lead bound to a companion also writes back at those milestones per
  `${CLAUDE_PLUGIN_ROOT}/references/companion-session.md` § Writeback.
- An epic run: after every merged story run the epic upkeep (`/we:epic` update: mirror, Updates Log,
  Learnings forward) and commit it before the next story starts. After a compact, rebuild state
  from the epic, git, the PRs and the tickets, never from the summary. The epic on the default
  branch is the backup; no extra documentation pass (owner 01.10.2026).
- After the merge, you run `/we:merged <PR>` yourself (§ Push, PR, CI step 5): it finds the run's branches
  and worktrees by `<KEY>` in git and the PR by number.
