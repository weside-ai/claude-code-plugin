# The board pane: `/board`

`/board` opens a pane beside the transcript with the workspace board: what waits for the owner,
which sessions run, who leads them and what each works on. An orchestrator session keeps the board
in one JSON file; the pane reads it and adds what it sees live of each running session. The pane
never writes the file; the owner answers a question with a button, which appends to a file of its own.

```text
◆ Board  as of 12 min ago (Orchestrator)

Waiting for the owner (2)
9 d  marketing  PROJ-41
  Storyline S1–S3
  [ Discuss ] [ More info ]
today  lead  PROJ-40  ✓ accepted 18:12 UTC (Orchestrator)
  Live test AC 16
  → tonight
  [ Accept ] [ Discuss ] [ More info ]

◉ lead [Lead]  PROJ-40  waiting  ● bypass
  Handoff
  P2 · test live

● CTA  PROJ-55  idle  ● bypass
  Bugs
  now: three workers
   ● chip  PROJ-57  #5560  busy  ● bypass
     Chip

Live, not on the board: stray
[ Refresh ] [ Flow ]  file 18:10 UTC · live 18:10 UTC · watch 3 s, all 1 min
```

## Opening it

`/board` opens the pane; the flow pane's **Board** button does the same, and the board's **Flow**
button opens `/flow` for what this session works on. Until `/board` runs in a session nothing
polls. Once open, the pane checks the file's modification time every three seconds and re-reads it
when it moved; every minute it re-reads the file and the live column whatever happened.

## The file

Default `~/.claude/we-state/board.json`; the plugin option `boardFile` names another one (`~/` and a
relative path count from the home folder). Without the file the pane says so and points here.

```json
{
  "updated": "2026-10-30T18:10:00+01:00",
  "updated_by": "Orchestrator",
  "priorities": ["…"],
  "owner_queue": [
    { "id": "Q1", "session": "lead", "key": "PROJ-40", "ask": "Live test AC 16",
      "since": "2026-10-30", "recommendation": "tonight" }
  ],
  "sessions": [
    { "name": "lead", "role": "master", "companion": "Lead", "parent": null, "keys": ["PROJ-40"],
      "topic": "Handoff", "now": "waits for the live test", "state": "wait-owner", "pr": null,
      "priority": 2, "direction": "test live", "note": null }
  ]
}
```

| Field | Meaning |
|---|---|
| `updated` | ISO timestamp of the last write; the header shows its age, yellow from 2 h, red from 8 h |
| `updated_by` | who wrote it, shown beside the age |
| `answer_prompts` | optional `accept`, `discuss`, `info` texts for the prompt a press sends (§ Answers) |
| `priorities` | free list for the orchestrator itself; the pane does not show it |
| `owner_queue[]` | questions only the owner can answer, oldest `since` (YYYY-MM-DD) first, its age in days yellow from 2, red from 7 |
| `owner_queue[].id` | the question's id; without one the row has no answer buttons |
| `owner_queue[].session`, `.key`, `.ask`, `.recommendation` | who asks, the ticket, the question, the asker's recommendation; **Accept** shows only with a recommendation |
| `sessions[].name` | the session's name as `claude agents` lists it; the live column matches on it |
| `sessions[].role` | `master` or `worker`; a session other sessions name as `parent` counts as a master |
| `sessions[].parent` | the master a worker reports to; workers are listed under it |
| `sessions[].state` | `build` or `ci` (● runs), `wait-owner` (◉ waits, listed first), `idle` or `done` (○ rests); anything else `?` |
| `sessions[].priority` | a number, lower first; sessions without one after those with one |
| `companion`, `keys`, `topic`, `now`, `pr`, `direction`, `note` | shown as written: name in brackets, ticket keys, topic, current step, PR number, `P<priority> · direction`, a warning line |

Every field but `sessions[].name` may be missing or `null`; the pane leaves it out.

## Answers

Each question with an `id` carries the buttons **Accept** (only with a `recommendation`),
**Discuss** and **More info**. A press appends one line to `board-answers.jsonl` in the board
file's folder (default `~/.claude/we-state/board-answers.jsonl`) and never writes `board.json`:

```json
{"id": "Q1", "answer": "accept", "ts": "2026-10-30T17:12:00.000Z", "session": "Orchestrator"}
```

| Field | Meaning |
|---|---|
| `id` | the question's `owner_queue[].id` |
| `answer` | `accept`, `discuss` or `info` |
| `ts` | when it was pressed, ISO UTC |
| `session` | the name of the session the pane was pressed in, as `claude agents` lists it; `null` when the live column does not know it |

The file only grows: the orchestrator reads it and removes the question from `owner_queue` once
handled. Until then the pane shows the newest answer beside the question (`✓ accepted 18:12 UTC
(Orchestrator)`), so nobody answers twice. It re-reads the file with the board's three-second watch.

When the pane runs in the orchestrator's own session, the one whose name equals `updated_by`, a
press also sends a prompt there, queued as if typed and run once the session is idle:
`<id>: proposal accepted`, `<id>: let's talk about it` or `<id>: I need more information`. The
board's optional `answer_prompts` words them in the orchestrator's own language, `{id}` standing
for the question's id: `{"accept": "{id}: Vorschlag angenommen"}`; a kind it leaves out keeps the
default. The pane finds its own name by matching its session id against `claude agents
--json`; a session without a name, or a pane in another session, only appends the line.

## The live column

Every minute `hooks/board/probe.py` runs `claude agents --json` and reads, per running session,
only the facts a verdict needs: busy, waiting, blocked, idle or gone; the `WE_ROLE` environment
variable as `master`, `worker` or `other`; the claude-swap profile's folder name from
`CLAUDE_CONFIG_DIR`; and the newest permission mode in the session's transcript. Of a process's
environment it looks at those two keys alone and prints neither value as read. A session that runs
but is not on the board is named in one line below the board.

The second `●` on a row is the start mode, with the permission mode as its label:

| Lamp | When |
|---|---|
| red | with `masterProfile` set: a master without `WE_ROLE=master`, a master outside that profile, or a worker inside it |
| yellow | the permission mode differs from the one most running sessions use |
| green | none of the above |

`masterProfile` is a plugin option naming the account folder master sessions run in, with or
without claude-swap's number (`me_example.com` matches `3-me_example.com`). Left empty, the three
red rules are off and only the yellow one holds.

## Requirements

Claude Code with function hooks (2.1.302 or later); for the live column `python3`, Linux
(`/proc`) and `claude agents`. The pane is part of the plugin's hooks module (`we/hooks/board/`); `answer.py` appends the answers.
