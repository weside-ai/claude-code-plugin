---
name: develop
description: >
  Dev-only worker: implements its chunk in its own worktree, runs local gates, commits, reports,
  stops — no PR, no CI, no ticket; pushes only on the brief's word. Triggers: "/we:develop",
  "implement only", "dev worker", or an /we:orchestrate dispatch.
argument-hint: '[<ticket-key> | <plan-path>] [--phases <N,M>]'
---

# /we:develop

Implement the chunk, run the local gates, commit, report, stop. The Lead's brief outranks every
default below; it never outranks a stop. Your final message is the report the Lead receives.
Contract, finish sequence and report fields:
`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md` § Dev-only worker contract, § Finish sequence,
§ Report.

## 1. Locate the plan

- A path argument is the plan. A key means `docs/plans/<KEY>-story.md`. No argument: ask the Lead
  or, invoked by a human, the human.
- `--phases N,M` limits the chunk to those `### Phase` blocks; absent means all phases.
- Invoked without a brief, run `${CLAUDE_PLUGIN_ROOT}/skills/story/references/plan-format.md` § The refined scan
  and stop on a failed item. A briefed worker skips it; the Lead ran it.
- An unanswered `## Open Fork` stops you. When the brief or the plan already carries the answer,
  build on it and name it in the report.
- With a ticket key, read the ticket with its comments (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`).
  A clarifying comment: build the newest statement and name the conflict. A comment that changes
  scope after the plan was approved: stop and hand it back as a question.

## 2. Worktree and branch

- Dispatched with `isolation: "worktree"`: you are already in your own worktree. Rename its
  `worktree-…` branch to the brief's branch (`git branch -m <type>/<KEY>-<slug>`) before the first
  commit. Dispatched with `cwd=<path>`: work there on the branch it has.
- A brief naming a base branch: `git merge <base>` first; your chunk builds on it.
- Run the bootstrap the brief names (repo source: `.weside/orchestrate.md`) and check its result
  before the first gate; a missing venv or database surfaces later as an unrelated error.
- Invoked by a human outside a worktree: `EnterWorktree(name="<type>/<KEY>-<slug>")`, then the same
  rename and bootstrap.

## 3. Implement

Read the plan completely, then implement its phases in order, inline. A file listed under both
your phases and a phase outside your `--phases` scope is a shared seam: name it in the report. Per
phase:

1. Tests per the brief's test discipline; brief silent → `test_discipline` in `.weside/config.json`
   (`tdd`: failing test first at each seam · `tests-after`, the default: tests after the code, same
   change · `off`: no new tests unless the plan asks). No implementation-coupled or tautological
   tests; mock only at system boundaries.
2. A new field flows end to end, not only into the model.
3. Regenerate and commit the generated artifacts the brief lists. Leave gate baselines to the Lead.
4. Commit the phase by path: `<KEY>: phase <N> — <what>` with the `Co-Authored-By:` trailer of the
   model running you.

## 4. Local gates

Run the commands yourself; they are deterministic. Scope and exceptions are in the contract:
affected tests only, service-bound tests skipped and listed, the named integration suite for a
critical chunk. A gate failure: fix, commit, re-run. The same gate red three times: stop.

## 5. Finish, when the brief makes you the last writer

Run the finish sequence through the Skill tool (`code-review` at `high`, `simplify`, `security-review` for money, auth or
tenant work, the ordered verification, the plan rewritten to what was built, the affected gates again) and commit after each step. The
brief says "not yours": skip it and say so. Invoked by a human: run it.

## 6. Report

First the self-review (`code-review` at `high`, per `worker-dispatch.md` § Dev-only worker
contract), unless step 5 just ran it. Push only when the brief says `Push: yes` (`git push -u origin <branch> && git ls-remote --heads origin
<branch>`; an empty answer is a blocker). Then end with the § Report fields as your final
message, one line per AC with its evidence. Stopping early is a report too: what you
completed, why you stopped, `blockers: <reason>`.
