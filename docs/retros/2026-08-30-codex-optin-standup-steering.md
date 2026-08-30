---
type: retro
pr: null
branch: main
analysed_at: 2026-08-30T02:40:00Z
ci_cycles: 0
scan_window: 0
auto_mode: false
proposals_total: 3
proposals_accepted: 3
proposals_deferred: 0
proposals_rejected: 0
applied_files:
  - we/references/worker-dispatch.md
  - we/references/agent-teams.md
  - we/skills/orchestrate/SKILL.md
  - we/skills/setup/SKILL.md
  - we/skills/develop/SKILL.md
  - we/skills/map/SKILL.md
  - we/skills/standup/SKILL.md
  - we/CLAUDE.md
  - CLAUDE.md
---

# Retro — Codex opt-in, /we:standup, mid-flight steering (6.1.0)

Not a cycle retro: no PR, no red CI, no correction loop. The source is three feature
requests plus one live experiment, and the PAIN section is honest about that.

## Wins

- The listing-budget gate from #45 did its job immediately: 318 chars of headroom forced
  the new skill's description to stay lean (final: 5,866 / 6,000 over 39 entries).

## Pain

- `/we:orchestrate` could dispatch to Codex from `execution.default: codex` alone, with no
  word from the user in that run.
  - evidence: `orchestrate/SKILL.md` executor table, `worker-dispatch.md` § Three worker backends
  - root: a persisted preference was read as a standing licence
  - root²: `execution.default` named two different things — the Claude tier (harmless) and
    the engine (consequential)

## Experiment — addressing a named agent without team tools

Both probes were spawned exactly the way `/we:council` spawns members:
`Agent(name=…, subagent_type="general-purpose", model="sonnet")`, then
`SendMessage(to=<name>, …)` from the lead. No team tool, no join step — the name is the address.

| Probe | Setup | Result |
|---|---|---|
| `probe-worker` | 8 sequential file reads; steer sent late | Obeyed, wrote the receipt — but it had **already finished** all 8 files. Proves the idle/resume path only. |
| `probe-slow` | 12 × `sleep 20` Bash calls; steer sent ~10 s in | **No receipt after 140 s.** The steer did not interrupt the tool chain. |

Docs (code.claude.com/docs/en/agent-teams.md) match the second result: messages queue in the
member's mailbox and are read at a turn boundary; there is no immediate-attention guarantee and
no documented latency for programmatic spawns. A worker sitting in a long tool call does not
look at its mailbox.

Second finding, not in the docs: both probes obeyed because the **hand-written prompt told them
to watch for lead messages**. The shipped Worker-Brief said nothing about inbound messages — it
only made outbound reporting mandatory. A steer to a default-briefed worker could have landed
and been read as noise. Hence the `INBOUND:` clause now in both briefs and in `/we:develop`.

What is still open for real life: whether a steer reliably lands mid-chunk on a worker doing
normal development work (edits, tests, git) rather than artificial sleeps. The turn boundaries
are much denser there, so the odds are better — but it is unmeasured. The rule shipped is
written to be true either way: verify by artifact, never by assumption.

## Decisions

- **P1 Codex opt-in — accepted.** Owner `worker-dispatch.md`; `orchestrate`, `setup`,
  `we/CLAUDE.md` cite it. Bug-hunt routing deliberately untouched: it keys on who *wrote* the
  code, which stays the right question.
- **P2 `/we:standup` — accepted, renamed.** Shipped as `status` first; renamed because `/status`
  is a Claude Code builtin and `status` already means the Lead's verbal roll-up inside
  `/we:orchestrate` (the same-term-two-meanings trap from `.claude/rules/plugin-authoring.md`).
- **P3 mid-flight steering — accepted, weakened to fit the evidence.** "Steering is normal
  instrument use" became "you can talk to a running teammate, but a sent steer is not a
  delivered steer." The earlier draft claimed the worker acts at its next turn boundary; the
  controlled test did not reproduce that, so it is not in the shipped text.
