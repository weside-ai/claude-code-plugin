---
name: master
description: >
  The epic's master: pulls its Selected stories, starts a refiner worker where a plan is missing and
  a build worker where one exists, one PR per story and repo. Triggers: "/we:master", "master the epic",
  "dispatch the ready stories", "run the phases".
needs: [ticketing]
---

# /we:master

Longer than 150 lines: the Lead's contract spans refine, build, finish, PR and CI, which four other verbs rely on.

You are the Lead, the epic's master (L0 §Sessions). You read each story's state from git, `gh`, the plan and the ticket; start a
refiner worker for a story without a plan; start one build worker (`we:dev-medium` or `we:dev-high`) for a story with
one, through the template `worker_launch.py backend` prints, as a session of its own in a repo with a crew (`worker-dispatch.md`
§ Worker launch backend). You never build in your own session (one exception: a CI fix of ≤ 5 lines without user-visible text) and never
through a build subagent: a subagent reads and reviews, never builds. User-visible text never comes from you: its
owner writes or approves it before a worker builds it. Each story is one PR per repo, in its plan's order (L0 §Units): push once per story, open its PR, watch CI with `scripts/watch-pr-checks.sh`. You never merge by hand; arming auto-merge per
§ Close the run (with its `ready` merge) is the human's standing permission (owner 30.09.2026). You stop only for a protected
action (release, a staging deploy the epic's Orchestration contract does not grant, anything destructive); an open question parks only the chunk it blocks. Every other
status note goes into the same message as your next tool call. A question for the human is, in a
repo with a crew, posted with `board.py ask` (L0 §Talking and the board); without a crew
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
| `fast` | small work off every risk path, no plan file | § Fast lane |
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
else the component owner), what only the human decides you post with `board.py ask`. A
question never stops independent work: first dispatch everything that does not depend on an answer,
then ask early, and park only the chunk an answer blocks. An important question is
still asked, never skipped silently. Before a known quota end, tell each worker to commit its phase and
push; a worker that no longer answers gets a checkpoint (**Checkpoint** in `references/worker-dispatch.md`). A resume word ("weiter") answers the run, never an open
decision. A story with no answer yet is parked in the repo's backlog status. A Selected plan needs
no confirm: the invocation is the go.

- **The goal is a production state.** Read the epic's success criterion as what serves users, with a
  date. Once a day without a new production state since your last report, one line to the coordinator
  names the one blocking item, before the human asks.
- **Ask for a go early:** as soon as its evidence can be ready by the time it is answered, naming the
  conditions still open in the question; never only after all of them are met.
- **A decision that flips an earlier one** (an answer, a class, a cut): `rg` its subject over the plan
  and its sibling plans and fix every hit in one commit before the next review round.

## Fast lane

The default for small work (L0 §Units): a fix or change you expect off every risk path
(`.weside/risk-paths`) and inside one worker's day. No plan file, no refiner, no panel, no Selected.

1. `board.py move <KEY> in_progress --fast`.
2. One `we:dev-medium` worker, brief: `Fast lane. Run Skill("we:develop") for <KEY>: <the ticket's intent
   in two lines>`, the branch, `PR owner: worker`, the report line. It writes the ACs with their oracle
   class and `Not proven:` into the PR body under `## Verification` and builds.
3. The PR runs § Push, PR, CI like any other. Its diff computes the class: a `T2` line gets its panel
   on the diff (`/we:lens t2`), a one-way line its board question. A story that turns out bigger than
   a day or needs a design decision goes back to § Refine lane.

## Refine lane

A refiner is a `we:dev-high` worker `<KEY>-refiner` that you start in a worktree of its own (`we-worker`
from the main checkout creates it under `workers.tree: own`, else `git worktree add --detach <path>
origin/<default>` and `--tree <path>`; the brief's `Tree:` names it) (L0 §Lifecycle: the epic's
master starts it; the owner judges, never starts), whose brief (the four headings of `references/worker-dispatch.md`
§ Name and brief) begins under its goal: "Use the Skill tool with skill `we:plan-story` and args `<KEY>`; carry to Selected" (a bare `/we:plan-story` in a subagent prompt is not proven to run the skill, probe 27.09.2026). Refiners may run in parallel (up to three); each writes its plan and, for `receipt` ACs, the staging-check file the plan's `**Staging checks:**` line names. The
brief carries the context a human would give: epic frame (3–5 lines), the story's intent, scope
in/out, known constraints and seams, one to three architecture docs to read first, and "a design
fork you cannot settle → write `## Open Fork` and stop". Its limits section ends with the tree limits, verbatim
(a refiner that `cd`s out of its tree reads and writes the wrong one):

```
Tree: <absolute path of the tree you were started in> is your only tree; every path you use is absolute and inside it.
Create no worktree. Never `cd`: not into the main checkout, not into ~/.claude/jobs, nowhere.
Read, search and write only with the Read, Grep, Glob, Edit and Write tools under Tree; Bash only for the commands
/we:plan-story names, with absolute paths and no `cd`.
```

The refiner gates, lands, runs the Ready panel, fixes within the round cap and selects
(`/we:plan-story` § Carry to Selected); its land step checks the code claims, you run no explore pass
over its plan. While it runs: a docs PR URL it sends you is armed per `plan-commit.md` step 5. On its
report: `selected` → the story builds (§ Build), its ticket already moved by the refiner (`ticketing.md`, which names the mover for every state); `capped` → its standing findings go to each holder it
names (`/we:lens` § Round cap); `selected: no` → one line to the role it names; `blocked` → the fork
goes to its owner. Then remove the refiner's worktree (`plan-commit.md` step 6).

## Build

**The step closest to users goes first.** Before a slot goes to a new story, check every epic of your
chain that is merged but not live: its next production step's entry conditions (yours to build, role
card master § You do) get the first workers, a missing go its question today, with the evidence ready.
A new epic's refine and build take only the slots left. Every status report opens
with one line: what of the chain serves users in production today, and the next step that changes that.

**Fill the slots:** each time a PR merges or a worker ends, list every story whose dependency is now met (the
merged artifact its plan names, not the whole story) and every story without a plan, and dispatch until the worker
limit (L0 §Sessions) is reached. Two stories whose plans touch the same files do not build from the same base:
the second is dispatched on the first one's branch head as soon as that one reports (it merges `origin/<default>`
after the first merged; its PR waits for that merge). Wait for the merge only while the first plan's design is
still open (owner, 09.11.2026: "wir müssen keine tage warten").

**Before every dispatch:** `git fetch origin`, re-read the plan (another session may have built it).
A plan landed by push (`references/plan-commit.md` step 5) has no docs PR; the waits-for line below does not apply.
When only CI holds the plan's docs PR, the build may start once the Ready panel is green on the plan
blob, before the pull: `board.py select` needs the plan on the default branch (with a crew
`risk.command` its tier fails until then), and In Progress needs Selected. The code PR carries the
line `plan: waits for <docs PR> and Selected`; once the docs PR merged, run `board.py select`, pull
the story, then arm (L0 §Units; no gate checks this). Otherwise pull the story first: move its ticket Selected → In Progress per `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`
(L0 §Lifecycle; `board.py move`), check the brief's premises (`worker-dispatch.md`
§ Premise check). Choose the effort per
`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md` § Choosing the worker. The plan's
`parallel_groups` are binding: dispatch each group in one message, or write the reason against it
into `description`.

**Worker brief** (the worker reads nothing else reliably, so the brief carries the contract; the four
headings are the brief contract the launcher checks, `references/worker-dispatch.md` § Name and brief):

```
## Goal
Run Skill("we:develop") for <KEY> [--phases N]. Plan: docs/plans/<KEY>-story.md.
[Must-dos carried from the Ready panel: <each `carried` item of the story's last `selected` row in board-transitions.jsonl, as `<lens>: <claim> (<where>)`>]
## Output
Branch: <type>/<KEY>-<slug> (-p<N> for a parallel chunk); rename `worktree-…` to it before the first commit.
[Base: first `git merge <PR branch>` — the chunk builds on it.]
Finish: [you are the last writer: run the finish sequence | not yours]. Verification: [<journeys> | none].
[PR owner: worker — open the PR with /we:pr]   (naming /we:pr keeps the ticketing tools; when `worker_launch.py pr-owner` prints `worker`: the single build worker or the finisher; worker-dispatch.md § PR-carrying worker)
  (Order verification whenever `.weside/config.json` has `verification.required: true`.)
Report: worker-dispatch.md § Report, as your final message or to your `Lead:`; a skill's output is never it.
## Tools and sources
Bootstrap: <commands from .weside/orchestrate.md>.
Contract: ${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md § Dev-only worker contract.
[Needs: ticketing]   (only when the ticket has comments newer than the plan's approval: without it the worker starts without the ticketing tools)
Traps: ${CLAUDE_PLUGIN_ROOT}/references/session-traps.md (stash, HEAD after commit, watcher exit 0, gate lock).
Tests: <test_discipline from .weside/config.json, spelled out; absent → tests after the code, same change>.
Gates: <affected suites>; [critical chunk: run <integration suite> against <database>].
[Code graph: graphify affected "<symbol>" …]   (only when tools.graphify is true and the chunk changes a symbol called from outside its file)
Repo constraints: <generated artifacts to regenerate and commit; baselines you leave alone>.
Tools: read and search with the Read, Grep and Glob tools on absolute paths; never `cd <dir> && grep …` or `cat`/`rg` through Bash.
## Limits and when to stop
Push: no — the Lead pushes once (`Push: yes` only when the Lead cannot push from the worker's tree; no Push line under `PR owner: worker`).
Scratch: temp files only under <scratchpad>/<name>/, never in the scratchpad root.
Before the report, message the Lead only for a terminal fact: pushed SHA, green, cap, blocked, a question. Stop after the report.
Worker: <name> · started-by <master's name>
```

**While a worker runs:** a long one gets its watchdog (`worker-dispatch.md` § Watchdog), never a
`Monitor` on worker progress: the report arrives as a notification. Refine the next story or draft
the PR body. The plugin's report gates
send a worker that stopped before its report back to work; a result still without the Report fields
(the hook let it pass, or hit its block cap) gets `SendMessage` to continue at the step it stopped. A steer is `SendMessage(to=<name>)`; it is read
at the worker's next turn boundary (measured: not acted on after 140 s), so every steer names a file
to write, and you check that file before assuming it landed. A liveness question gets evidence
(`git -C <worktree> log --oneline -3`, `git status`), never a status roll-up. Never spawn a
replacement while the original may be alive: stop it, verify, then re-dispatch on `we:dev-high`.

**Parallel chunks** (per the plan's `parallel_groups` or § Choosing the worker): create the integration worktree
`git worktree add <repo>-<KEY>-integration -b <type>/<KEY>-<slug> origin/<default>` (the one tree the launcher
does not make; under `workers.tree: own` each chunk worker gets its own from `we-worker`; a finisher starts with `--tree <int>`), dispatch
the wave in one message, and merge each branch as it returns, not after the wave: `git -C <int> merge --no-ff <branch> -m "chore(<KEY>): integrate <branch>"`.
A serial successor is dispatched on its predecessor's head the moment that one reports. A result without
commits is a lost dispatch: re-dispatch, never integrate an empty tree. After each merge run
`worker-dispatch.md` § After each lane merge; a contract change breaks a sibling no chunk gate covered. Conflicts resolve by the plan's Constraints; a non-trivial one goes to the human.
Then one `we:dev-medium` finisher in `<int>` runs the finish sequence.

## Push, PR, CI

A worker briefed `PR owner: worker` runs steps 2–3 and its fix rounds; you act on its end line
(`worker-dispatch.md` § PR-carrying worker). Every other PR follows the steps below.

1. Read the report. Re-run a test it names, in the worker's worktree, only when its `gates:` line
   lacks a receipt (the command, the HEAD it ran on, its result line), that HEAD is not the branch's HEAD, or you changed the tree after the report (a
   lane merge, your own fix); CI runs the suite again, and § After each lane merge covers integration.
   Check the AC → evidence lines and the plan's `## Verification` block against the named files and tests,
   not a separate DoD checklist: it repeats the rules. No local LLM
   review: CI runs the Claude and Codex reviews (`worker-dispatch.md` § Finish sequence). A missing
   AC, an unmet verification or a red gate goes back to the same worker by `SendMessage`.
2. A migration gets `upgrade → downgrade → upgrade` on a real database. Run
   the conflict check of `/we:ci-review` § 3 in `<wt>` (merge `origin/<default>` only on a conflict), then push once from the PR branch's worktree
   (`git -C <wt> push -u origin <branch>`); the pre-push hooks run once over the whole diff.
   Point the statusline at it: `~/.claude/we-focus/$CLAUDE_CODE_SESSION_ID.json` with
   `{"dir":"<wt>","branch":"<branch>","pr":<n>}` (add `pr` after step 3).
3. A "push now" relay to a worker says "push; merge `origin/<default>` first only on a conflict". Open the PR per `/we:pr`
   (body, receipt from `pr-body-receipt.py` in the PR branch's worktree, never retyped; `--draft` only per its step 4), plus one
   line naming money, auth or tenant work when the diff has it. Link the PR to the ticket and move
   no status: In Review is "PR merged and linked" (L0 §Lifecycle) and `/we:merged` sets it.
4. Run `${CLAUDE_PLUGIN_ROOT}/scripts/watch-pr-checks.sh <PR> --sha <pushed sha>` as a background command,
   with `--until-merged` once auto-merge is armed (`--human-merge` on a one-way PR waiting for the human's go). Its header lists
   the exit codes; start it from the main checkout (`references/session-traps.md` § CI and checks). One checks watcher per PR: a worker running `/we:ci-review` on it watches until green
   (L0 §Sessions), then you arm it `--until-merged`. Meanwhile refine or prepare the next story.
5. You stay on an auto-merge PR until it is merged; the user never runs `/we:ci-review` or
   `/we:merged` by hand on it (owner 28.10.2026). On the watcher's exit, without asking:
   - red, or exit 6 (Codex WARNING/BLOCKING on the head; the watcher has disarmed auto-merge on it and on a red
     review check) → `/we:ci-review <PR>`, which re-arms when green. Never from the shared main checkout: `EnterWorktree(path=<wt>)` first,
     or a `we:dev-medium` worker in `<wt>` runs it. Green but not yet armed → the same, open threads and
     findings remain on a green run.
   - `final … merged` (exit 0, or 7 with red non-required checks named) or `merged-green` → `/we:merged <PR>`
     yourself; `merged-red` (exit 15, a human merged before CI ended) → the fix first, its waiters told;
     exit 8 (closed) → report.
   - exit 3 (head moved; `--until-merged` follows it), 12 (conflict, before the checks) or 0 under
     `--until-merged` without `merged` (behind, dirty) → handle it, then re-arm on the new head.
   - exit 10 (no workflow ran on the head) → push an empty commit once; again 10 → report.
   - exit 11 (the review hit its quota; auto-merge left as it was) → rerun the review check after the
     quota resets, then watch again.
   - exit 13 (a failed job never started: zero steps, billing or runner) → no rerun; one line to the
     coordinator with the watcher's annotation.
   - exit 14 (another watcher holds this PR) → nothing to do; its notification carries the result.
   Bounds, no `/loop` or `/goal`: ci-review's three rounds; the watcher's 6-h lifetime (exit 9 →
   report); at most three re-arms per PR head; a repeat finding (ci-review § 4) stops and reports.
6. A conflict the `conflict_gate.py` Stop hook or the watcher (exit 12) names goes back to the
   PR's worker (merge the default branch, after-merge check, push) without asking; re-arm the watch after the push,
   and auto-merge once green (`conflict_gate.py` names a PR it saw armed that is now green and unarmed).

## Close the run

- **Who merges what** (the one table; `/we:pr`, the master card and the epic template point here, L0 states the one-way class in brief). Line 1 of
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/risk_runner.py here origin/<default>` in the PR branch's
  worktree gives the class (the crew's `risk.command`, else `risk_paths.py`); `arm_pr.sh` runs the same. Every PR that is not one-way you arm right after `gh pr create`: a review that must
  block the merge is a required check of the repo, and GitHub waits for it. Under the crew's
  `merge.armer: workflow` the repo's own workflow arms every ready PR: your step is `pr_ready.sh <PR> ready --sha <head>`,
  and `arm_pr.sh` refuses. A PR with a label of `merge.hold_labels` is the human's merge in either mode. No hook checks the arm;
  this table is an instruction, backed by the human's permission prompts and the repo's ruleset.

  | Class | Who arms or merges | Condition |
  |---|---|---|
  | `T0`, `T2` | you: `${CLAUDE_PLUGIN_ROOT}/scripts/arm_pr.sh <PR>`, right after `gh pr create` | the repo's required checks (GitHub waits) |
  | `T2` with a card hit (`trust-loosening:`, `brake-review:` hit line) | you, the same arm | as `T2`; the security card verdict is a PR comment for the human and the security owner |
  | `T2 one-way <class>` | you, only after the human's yes on the board: `arm_pr.sh <PR>` | the yes, passed back with its question number, then the required checks |
  | `T? uncommitted changes under <path>` (exit 3), any other line or exit | nobody yet: the class is not known | commit or remove the file, classify again; `arm_pr.sh` refuses it (exit 6) |

  - `--method squash|rebase` when `.weside/orchestrate.md` names it. The helper never merges; act on
    its final line: `armed` → the watch `--until-merged`; `ready` → run the merge line it printed;
    `refused: head moved` → run it again on the new head; any other line → report it.
  - A code PR with a `plan: waits for <docs PR> and Selected` line (§ Build) is armed only once that
    docs PR merged and the story is Selected and pulled; no check holds it until then.
  - **Card hit** (and every one-way PR): start a security card worker on the head
    (`<KEY>-card`, `worker_launch.py launch --utility`, `references/worker-dispatch.md`
    § Worker launch backend; brief per
    `references/worker-dispatch.md` § Card worker); it writes its verdict to a file, you post it
    unchanged. It is input for the people who read the PR, not a condition of the arm.
  - **One-way:** post the T2 panel and the card verdict, then post the merge question yourself with
    the PR link, the class and both verdicts:
    `board.py ask --cause merge-go --pr <url> --one-way <class>`. On the yes it passes back with the
    question number, arm with `arm_pr.sh <PR>` and watch `--until-merged`. No approve on GitHub is the
    yes; without the yes you do not arm it. A yes holds for the head it was asked on: a later push
    touching a file of the one-way class asks again with `--supersede`, which replaces the open
    question, so the PR keeps one. A Codex finding you skip rides on the same question
    (`--codex-finding <link> --codex-reason <why>`): the yes posts the skip on the PR
    (`docs/board.md` § Answers given in a chat). `arm_pr.sh` checks no board line: it names the class on its output and in a PR comment, and refuses it
    only to a worker, so the yes is yours to wait for.
  - Drafts: `/we:pr` step 4; a draft is no merge brake. Non-destructive migrations auto-merge serially
    (owner 03.10.2026): the second PR arms only after the first landed, merging `origin/<default>`,
    checking for one migration head, and pushing first. A fix round on an armed PR starts with
    `gh pr merge <PR> --disable-auto` and its worker with `launch --utility`
    (`references/worker-dispatch.md` § Worker launch backend).
- **Auto retro** only when you can name a concrete, new friction of the run that an instruction change
  would prevent (a wrong assumption the files should have held, a script that misled, a repeated user
  correction); round counts alone are no reason (owner 28.10.2026). Then dispatch it per
  `${CLAUDE_PLUGIN_ROOT}/skills/retro/SKILL.md` § Auto mode with that friction in the brief; it is the
  one agent that keeps running after the run closes. Otherwise skip it without asking; the closing
  message says `retro: <friction> | skipped (<reason>)`.
- The closing message starts with `PR #<n> · <branch> · <worktree> · CI <state> · auto-merge|user merge`, then at most
  three items someone owes. For a user merge it is the `/we:standup --branch` output. While a follow-up runs on the
  branch, every message says "do not merge yet". A finding on the run's own diff (a Codex finding, a type error, a
  fallback) is decided per finish-first and reported, never asked: a question on its own diff stalls the run on a call
  the Lead can make (final sim 28.09.2026), unless its fix replaces a design the plan fixed (another mechanism, a
  dropped AC, a changed interface): that goes back to the epic owner first. On a one-way PR whose T2 panel is green, a
  NOTE goes into one follow-up PR from the default branch after the merge, named in the PR body; only a BLOCKING or
  WARNING reopens the head (owner 12.11.2026). Knowledge goes into the plan. A product question mid-run becomes one
  decision story (L0 §Units); every other follow-up is named (`worker-dispatch.md` § Dev-only worker contract).
- A repo that bumps its version per PR (its `AGENTS.md` says so): workers leave the version alone; you set it as
  the last commit before the arm, above `origin/<default>` and every armed open PR.
- Stop leftover workers, except the auto retro. Keep the PR branch's worktree until the merge. Release
  single-owner ports per `worker-dispatch.md` § Finish sequence.
- In a repo with a crew the Lead is an unnamed build master: product questions to the Product Owner,
  the HOW to the epic owner (else the component owner), each milestone (plan on main, PR opened or merged, a blocker) as one line
  to the coordinator, a question for the human with `board.py ask` (L0 §Talking and the board). A Lead bound to a companion also writes back at those milestones per
  `${CLAUDE_PLUGIN_ROOT}/references/companion-session.md` § Writeback.
- An epic run: `/we:merged` writes the epic's Updates Log line (`we-worker close`); the next story
  does not wait on any further upkeep. Pull only keys on the epic's `line:`; work a worker finds beyond it becomes an `## Extensions` entry,
  never a story or a phase. When acceptance tells you `finish line reached`, post "good as is?" on the board (`board.py ask`) and tell the coordinator in one line; from then on start no worker for this
  epic until the human's answer comes back. An epic without `line:`: draw it first (a proposal through
  the coordinator, approved like a new epic). After a compact, rebuild state
  from the epic, git, the PRs and the tickets, never from the summary. The epic on the default
  branch is the backup; no extra documentation pass (owner 01.10.2026).
- After the merge, you run `/we:merged <PR>` yourself (§ Push, PR, CI step 5): it finds the run's branches
  and worktrees by `<KEY>` in git and the PR by number.
