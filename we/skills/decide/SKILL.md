---
name: decide
description: >
  Escalation as one decision story: both owners' positions, costs and reversibility in one record
  that routes itself past the SLA. Triggers: "/we:decide", "we disagree", "escalate this".
---

# /we:decide

Two role holders who disagree on one story write one decision story with
`board.py escalation open`, settle it themselves within the crew's `sla.hours`, and otherwise let the
coordinator's `escalation route` hand it on. A two-way door (`--reversible yes`) proceeds on the
master's default meanwhile; a one-way door waits. Format and stages: `${CLAUDE_PLUGIN_ROOT}/docs/board.md` § Escalations.

## 1 · Open (a session holding one of the two roles)

Gather both positions before the call; ask the other party for theirs when the chat lacks it.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board.py escalation open --key <KEY> \
  --parties <your-role>,<their-role> --question "<one decision, one line>" \
  --a "<first party's position>" --a-cost "<what it costs>" \
  --b "<second party's position>" --b-cost "<what it costs>" \
  --reversible <yes|no> [--touches <vision|money|law|priority>]
```

- `--a` belongs to the first role in `--parties`, `--b` to the second.
- `--touches` when the question decides vision, money, law or the priority between areas: the record
  then skips the escalation role's decision and goes to the human's bundle past the SLA, with the
  escalation role's recommendation in front of it.
- A refusal (neither role held, a missing field, a role key outside the crew's) writes nothing:
  fix the call, never write the record by hand.
- The last stdout line `carry: [...]` (ticketing `jira`) holds a `comment` op: post it on the
  story's ticket with the ticketing MCP and re-read the comment.
- A `warning: <pair>: more than two escalations this week` line goes to the coordinator: the right
  in `crew.json` between those roles is drawn wrong, and that gets fixed, not the escalation path.

Good: `--question "Paywall in v1?" --a "no paywall, free launch" --a-cost "two weeks of revenue"`.
Bad: `--question "Pricing and launch plan"`: two decisions, no one can settle it in one line.

## 2 · Settle

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board.py escalation settle E<n> --outcome "<what holds now>"
```

- Stage `self`: either party settles. Stage `escalation`: the role it waits on (`waiting_on`).
- Stage `bundle`: the coordinator settles with `--via human` after the human's answer on the board
  item `E<n>`; a `--touches` record refuses until `advise` is in.
- Carry the `carry:` line as in § 1, then tell the other party the outcome.

## 3 · Advise (the escalation role, `--touches` records only)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board.py escalation advise E<n> --recommendation "<advice>"
```

## 4 · Route and count (the coordinator)

`board.py bundle` runs `escalation route` first. Between bundles: `board.py escalation route` moves
every record past its `sla_due` and prints one `route: E<n> <KEY> <from> → <to>` line per move;
`board.py escalation count` prints the records per role pair in this ISO week.

## Done when

- [ ] the record `E<n>` exists in `board-escalations.jsonl` and its `carry:` comment is on the ticket
- [ ] the record is settled, or its `stage` and `waiting_on` name who decides next
