---
name: harness-review
description: >
  Harness review: measures the crew's last 14 days, asks each role its top friction, runs the
  deletion test over rules, gates and skills, lets a fresh agent attack the result; writes one ranked
  plan and inbox entries for /we:optimize. Triggers: "/we:harness-review", "review the harness".
---

# /we:harness-review

1. The output is one plan file and inbox entries, never an edit to a rule, gate or skill:
   `/we:optimize` decides what changes. Store format and where its commits land:
   `${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md`.
2. A finding counts only with a number from step 1, a role's answer from step 2, or a file and
   line a reader can open. A subagent's finding is checked at its cited line before it counts:
   agents report confident claims that the file does not hold.
3. The hr role runs it, with a crew; without one, the user. The plugin's own checkout: print, write
   nothing (`optimization-store.md` § Plugin checkout and workspace).

Invocation: `/we:harness-review` (14 days) · `--since <n>d` · `--no-ask` (skip step 2).

## 1 · Measure

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow_report.py" --since 14d --md
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow_intervals.py" --since 14d --html "${TMPDIR:-/tmp}/flow.html" --no-ci
```

`--no-ci`: a cold CI read over 14 days outlasts the Bash tool's two-minute timeout; the report above
reads the required checks per head itself.

Read from the report: `Flow efficiency` and `Waiting by kind` (who waits on whom, in hours), the
heads and rounds per code PR, `Required checks: red heads` (`rerun green` is a false alarm),
`Brakes per day` and `Brake outcomes`. A brake line no `outcome` judged counts as a false alarm:
a brake that does not count its stops cannot show it pays (`product`, 12.11.2026).

Then follow the work: an inventory finds only what is already on a list. Take five merged stories
(small, feature, tooling), and give every minute from the first sign of work to the merge one class
(work, machine, waiting for a slot, lock or queue, waiting for a person, rework with its cause,
unknown) from `flow_intervals.py`'s rows and the logs; rank the causes. A cause on no inventory of
§ 3 joins the deletion test there, and each `unknown` names the log that is missing.

- [ ] the report file under `reports/` exists, or the run printed why not
- [ ] every `n/a` row is named with its missing source, never read as zero
- [ ] five stories traced, their minutes per class and the ranked causes noted
- [ ] the three largest waits in hours and every brake's danger / false alarm / unjudged counts are noted

## 2 · Ask the roles

`crew.py members` lists the crew; `ListAgents` shows who runs. One `SendMessage` per running
member (never to yourself, never to a worker: its master answers for it), all with the same
question:

> HARNESS · <your name> asks: what in how the crew works cost you the most time in the last
> 14 days (a wait, a gate, a rule, a step)? Reply with one line `FRICTION · <name> · <what> ·
> <how often> · <hours lost, estimated> · <what you would cut>`, or `FRICTION · <name> · nothing`.
> Finish your current step first.

Track replies as `/we:retro` § Broadcast step 2 does; a member silent after its current step is
named, never waited on. Without a crew, ask the user the same question once.

- [ ] one row per asked member: the reply, or `silent`

## 3 · Deletion test

The inventory: the repo's always-loaded rules (`AGENTS.md`, `.claude/rules/**` without `paths:`),
the hooks and gates in force (`hooks.json` of each plugin, the default branch's required checks,
the gates in `.weside/config.json`), the skills the crew invokes. Delegate the sweep to one
`we:explore-medium` with this list and the question; check each answer at its line (rule 2).

Per item: what would break if it went? It stays when it names a measured failure it prevents
(a brake judged `danger: yes`, a ledger or inbox evidence line, an incident in `git log`) or a
reason a reader needs. Otherwise it is a candidate:

- a rule with neither → cut, or one line at the place the case occurs that says why
  (`${CLAUDE_PLUGIN_ROOT}/AUTHORING.md` § Guideline before rule);
- a gate or brake that in the window stopped more without the danger than with it, or that has
  no finding that would have stopped a merge → cut, not rebuilt (`product`, 12.11.2026);
- a gate a session can write green itself, or one that is neither leak protection, damage
  limitation nor a brake before an irreversible action → input for a human, off the merge path.

| Bad | Good |
|---|---|
| "cut `draft_reason_gate`: feels like ceremony" | "`draft_reason_gate`: 9 brakes, 0 `danger: yes`, 0 merges stopped in 14 days; cut; saves ~1.5 h of re-pushes" |

- [ ] every inventory item has `stays (<failure or reason>)` or a candidate line with its numbers

## 4 · Draft and attack

Write the plan (step 5's file): one finding per row, ranked by hours saved in 14 days, each with
its number and source; a finding without a number ranks last as `unmeasured`. Hours come from step
1 (waiting hours, runner and agent hours, rounds per PR, wait to merge) or a step-2 estimate,
marked as such.

Then one fresh `we:explore-medium` gets only the plan's path and the sources it cites, never
your conclusions: "Attack this plan. Which finding is wrong, which cut breaks
something, which large cost is missing? Each claim with file:line or a number." Check every claim
at its line. A confirmed claim changes the plan; an unconfirmed one is dropped and counted in the
plan's last line.

- [ ] every adversary claim is marked `confirmed` or `dropped (<why>)`

## 5 · Write

- **Plan:** `.weside/optimization/reviews/<YYYY-MM-DD>-harness.md`: the window, the measured
  table's key numbers, the role replies, the ranked findings, the adversary tally.
- **Inbox:** one entry per finding through `retro_write.py inbox/ <file>` (store reference
  § Inbox entry): a cut is `pattern: sunset`, `action: remove`; a friction with a remedy is
  `pattern: gap` or the matching id; `source: review`, the evidence line names the plan file and
  the hours.
- Commit per the store reference § Layout (where store commits land).

Close with one line: findings, hours saved in total, inbox entries written, and `/we:optimize` as
the next step.

## Rules

- A role's answer is evidence of a friction, not of its size: the hours in the ranking come from
  step 1 wherever it measures the same thing.
