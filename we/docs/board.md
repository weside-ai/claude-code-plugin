# The board pane: `/board`

`/board` opens a pane beside the transcript with the workspace board: what waits for the owner (you),
which sessions run, who leads them and what each works on. An orchestrator session keeps the board
in one JSON file; the pane reads it and adds what it sees live of each running session. The pane
never writes the file; the owner answers a question or marks a news item read with a button, which
appends to a file of its own.

```text
◆ Board  as of 12 min ago (Orchestrator)
████████░░░░  2/3 masters active · 2 waiting for you
1 in CI
Finish what is open → money → marketing.

╭──────────────────────────────────────────────────────────╮
│ News (2)                                                 │
│ [ Read ] ⚑ v2.4.1 is tagged, prod still reports …  today │
│            The rollout hung on a GitHub 502 and was      │
│            restarted; the lead re-tests once it is live. │
│ [ Read ] ◉ Sign the processor agreement in the bil…  2 d │
╰──────────────────────────────────────────────────────────╯

[ ▸ Notes ]  older free text, folded to its first line

╭──────────────────────────────────────────────────────────╮
│ Waiting for you (2)                                      │
│                                                          │
│ Q2  9 d  marketing  PROJ-41                              │
│ Storyline S1–S3                                          │
│ [ Deny ] [ Discuss ] [ More info ] [ Update ]            │
│                                                          │
│ Q1  today  lead  PROJ-40                                 │
│ Live test AC 16                                          │
│ → tonight                                                │
│ [ Accept ] [ Deny ] [ Discuss ] [ More info ] [ Update ] │
│ ✓ accepted 18:12 UTC (Orchestrator)                      │
╰──────────────────────────────────────────────────────────╯

╭──────────────────────────────────────────────────────────╮
│ ◉ lead  [Lead]  PROJ-40  waiting  ● bypass  [ ▸ Work ]   │
│ Handoff                                                  │
│ waits for the live test                                  │
│ P2 · test live                                           │
╰──────────────────────────────────────────────────────────╯
╭──────────────────────────────────────────────────────────╮
│ ● CTA  PROJ-55  idle  ● bypass  P3  [ ▾ Work ]           │
│ Bugs                                                     │
│ three workers                                            │
│ Saga Reliability (active)                                │
│   Epic PROJ-55 Bug sweep (selected) · 1/4 stories merged │
│     ● PROJ-57 Chip state per plan  CI                    │
│     ● PROJ-58 Retry on 502  build                        │
│     ● PROJ-59 Cancel twice  approved                     │
│                                                          │
│ └ ● chip  PROJ-57  #5560  busy  ●  CI running            │
╰──────────────────────────────────────────────────────────╯

[ + 2 idle/other ]

[ Refresh ]  [ Flow ]
file 18:10 UTC · live 18:10 UTC · watch 3 s, all 1 min
● runs  ◉ waits for you  ○ rests  ? unknown
second ● = start mode
```

## Layout

From the top: the header with the board's age and a counter (a bar of the masters by lamp, how many
are active, how many questions wait for you, how many sessions are in CI), the `priorities` line, the
unread `news` in one frame (§ News) and, when set, the older `notes` folded to one line. Then one frame with every question, oldest first, and one frame per
master with its workers inside, each worker on one line cut to the pane. A master whose group neither
runs nor waits (`idle` or `done`, workers too), a headless worker group at rest and every session
running but not on the board fold into the last line, **+ N idle/other**, which opens and closes
them. The frame's border takes the master's lamp colour, red when its start mode is red. The pane
breaks a header line between its parts, never inside a frame, so it stays readable at 60 columns.

## News

`news` is a list of short items the orchestrator wants the owner to see, each on one line:

```json
"news": [
  { "id": "N3", "kind": "gate", "title": "v2.4.1 is tagged, prod still reports v2.4.0",
    "body": "The rollout hung on a GitHub 502 and was restarted; the lead re-tests once it is live.",
    "ts": "2026-10-30T20:40:00+01:00" },
  { "id": "N2", "kind": "todo", "title": "Sign the processor agreement before Friday", "ts": "2026-10-28" },
  { "id": "N1", "title": "Kernel runs on its own until the money stories merged" }
]
```

| Field | Meaning |
|---|---|
| `id` | required, unique across `news` and `owner_queue` (both answer into one file); a changed message takes a new id |
| `title` | required, one line, bold; cut to the pane's width |
| `body` | optional detail, dimmed and indented under the title; keep it to a few lines |
| `ts` | optional date or ISO timestamp; shown as its age (`today`, `2 d`) |
| `kind` | optional: `info` (`•`, the default), `gate` (`⚑`, something blocks), `todo` (`◉`, the owner must act) |

The list keeps the file's order, so the orchestrator puts the newest or most urgent first. Each item
carries **Read** in front; a press appends a `read` line to the answers file (§ Answers) and the item
leaves the pane at once. The orchestrator reads those lines and prunes the items from `news`; until
it does, an item whose newest line is `read` stays hidden. With every item read the frame is gone.

`notes`, the older single string, still works: it folds to **▸ Notes** and its first line, dimmed,
and opens to the whole text on a press. A new board writes `news`.

## Work

A master whose group carries ticket keys (its own `keys` and its workers') or a `work` tree has a
toggle last in its title: **▸ Work** closed, **▾ Work** open. Every box starts closed; the pane
remembers per master which are open, across refreshes and restarts. Open, the box shows a compact
tree of the work in progress:

```text
Saga <title> (status)
  Epic <KEY> <title> (status) · n/m stories merged
    ● <STORY-KEY> <title>  <phase>
PROJ-99 (no plan)
```

The tree grows from the keys, read like `/flow` reads them: the plan files `docs/plans/*-saga.md`,
`*-epic.md` and `*-story.md` on the default branch of the repo the master runs in (`cwd`), linked by
their frontmatter (`story`, `epic`, `saga`, `ticket`, `status`, the first heading), and the stories'
PRs from `gh`. A key that is an epic brings the epic with all its stories; a story brings its epic, or
stands alone without one; an epic with a `saga` sits under it. A key without a plan file is a leaf
`<KEY> (no plan)`. The lamp is the story's `/flow` phase: `plan`, `approved`, `build`, `PR`, `CI`,
`CI red`, `PR closed`. Merged stories only count in their epic's line. The group's own stories lead
their epic, then the most urgent; at most eight story lines, the rest as `+ k more`.

Nothing is read while a box is closed. Opening one derives its tree; once open, the trees refresh
every two minutes like `/flow`, with one `git fetch` per repo for all its open boxes; **Refresh**
fetches again. A master without `cwd` says so in its box.

A session's `work` field is a ready tree that replaces the derived one, for a repo without plan
files. It needs no `cwd` and nothing is fetched for it:

```json
"work": [
  { "kind": "saga", "title": "Brand refresh", "status": "active", "children": [
    { "kind": "epic", "key": "LC-12", "title": "Launch kit", "status": "selected", "children": [
      { "kind": "story", "key": "LC-13", "title": "Press page", "phase": "dev" },
      { "kind": "story", "key": "LC-14", "title": "Logo files", "phase": "merged" },
      { "kind": "story", "key": "LC-15", "title": "Fact sheet", "status": "drafting" }
    ] }
  ] }
]
```

| Field | Meaning |
|---|---|
| `kind` | `saga`, `epic`, `story`, or `key` (a leaf without a plan) |
| `key`, `title`, `status` | shown as written; a story's `status` stands where the lamp would without a `phase` |
| `phase` | a story's lamp, one of `/flow`'s phases: `idea`, `draft`, `refined`, `dev`, `ci`, `ci-red`, `ready`, `merged`, `closed` |
| `children` | a saga's epics, an epic's stories |

## Opening it

`/board` opens the pane; the flow pane's **Board** button does the same, and the board's **Flow**
button opens `/flow` for what this session works on. Until `/board` runs in a session the pane polls
nothing; the deliverer (§ Answers) checks the board file every three seconds in every session, pane or not, and acts only in the orchestrator's. Once open, the pane checks the file's modification time every three seconds and re-reads it
when it moved; every minute it re-reads the file and the live column whatever happened.

The option `boardAutoOpen` (`/plugin` → we → Configure) opens it at session start: `off` (default),
`on` (every session), `orchestrator` (only the session whose companion pin holds `roles.coordinator`
in the repo's crew, checked by `scripts/crew.py is-role coordinator`; working mode:
`references/working-mode.md`). Opened unasked, the pane needs 144 terminal columns and waits
undrawn below that until you widen the terminal or run `/board`.

## The file

Default `~/.claude/we-state/board.json`; the plugin option `boardFile` names another one (`~/` and a
relative path count from the home folder). Without the file the pane says so and points here.

```json
{
  "updated": "2026-10-30T18:10:00+01:00",
  "updated_by": "Orchestrator",
  "priorities": ["…"],
  "news": [
    { "id": "N1", "kind": "gate", "title": "v2.4.1 is tagged, prod still reports v2.4.0", "ts": "2026-10-30" }
  ],
  "owner_queue": [
    { "id": "Q1", "session": "lead", "key": "PROJ-40", "ask": "Live test AC 16",
      "since": "2026-10-30", "recommendation": "tonight" }
  ],
  "sessions": [
    { "name": "lead", "role": "master", "companion": "Lead", "parent": null, "keys": ["PROJ-40"],
      "topic": "Handoff", "now": "waits for the live test", "state": "wait-owner", "pr": null,
      "priority": 2, "direction": "test live", "note": null,
      "cwd": "/home/me/work/lead", "session_id": "0b5c1e2a-7f3d-4c11-9a8e-1d2f3a4b5c6d" }
  ]
}
```

| Field | Meaning |
|---|---|
| `updated` | ISO timestamp of the last write; the header shows its age, yellow from 2 h, red from 8 h |
| `updated_by` | who wrote it, shown beside the age |
| `answer_prompts` | optional `accept`, `deny`, `discuss`, `info`, `update` and `update_asker` texts the deliverer sends (§ Answers) |
| `priorities` | a list or one string; the pane shows it as one dimmed line under the header, a list joined with ` · ` |
| `news[]` | optional: short items with `id`, `title`, `body`, `ts`, `kind`, each with a **Read** button (§ News) |
| `notes` | optional, older: one free text, folded under the news to its first line (§ News) |
| `owner_queue[]` | questions only the owner can answer, oldest `since` (YYYY-MM-DD) first, its age in days yellow from 2, red from 7 |
| `owner_queue[].id` | the question's id; without one the row has no answer buttons |
| `owner_queue[].session`, `.key`, `.ask`, `.recommendation` | who asks, the ticket, the question, the asker's recommendation; **Accept** shows only with a recommendation, **Deny** always |
| `sessions[].name` | the session's name as `claude agents` lists it; the live column matches on it |
| `sessions[].role` | `master` or `worker`; a session other sessions name as `parent` counts as a master |
| `sessions[].parent` | the master a worker reports to; workers are listed under it |
| `sessions[].state` | `build` or `ci` (● runs), `wait-owner` (◉ waits, listed first), `idle` or `done` (○ rests); anything else `?` |
| `sessions[].priority` | a number, lower first; sessions without one after those with one; shown as `P<n>` in the title, or before `direction` |
| `sessions[].cwd`, `.session_id` | optional, never shown: the directory the session runs in and its Claude Code session id, so the orchestrator keeps the list of its masters and can restore one after a workspace crash in the right directory with `claude --resume <session_id>`; a master's `cwd` is also the repo its work tree is read from (§ Work) |
| `sessions[].work` | optional: a master's ready work tree, which replaces the derived one (§ Work) |
| `companion`, `keys`, `topic`, `now`, `pr`, `direction`, `note` | shown as written: name in brackets, ticket keys, topic (dimmed), current step, PR number, `P<priority> · direction`, a warning line; a worker shows lamp, name, keys, PR, live status, start lamp and `now` on one line |

Every field but `sessions[].name` may be missing or `null`; the pane leaves it out.

## Answers

Each question with an `id` carries the buttons **Accept** (only with a `recommendation`), **Deny**,
**Discuss**, **More info** and **Update**; each news item carries **Read**. A press appends one line to `board-answers.jsonl` in the board
file's folder (default `~/.claude/we-state/board-answers.jsonl`) and never writes `board.json`:

```json
{"id": "Q1", "answer": "accept", "ts": "2026-10-30T17:12:00.000Z", "session": "Orchestrator"}
```

| Field | Meaning |
|---|---|
| `id` | the question's `owner_queue[].id`, or the item's `news[].id` |
| `answer` | `accept`, `deny`, `discuss`, `info` or `update` for a question; `read` for a news item |
| `ts` | when it was pressed, ISO UTC |
| `session` | the name of the session the line was written in, as `claude agents` lists it; `null` when the live column does not know it |
| `via`, `quote` | only on a line `board.py answer` wrote: `chat`, and the owner's own words when given |

The file only grows (`answer.py` and `board.py` append with `O_APPEND`, nothing rewrites it); the
orchestrator removes the question from `owner_queue`, or the item from `news`, once handled. The pane
shows the newest answer beside the question (`✓ accepted 18:12 UTC (Orchestrator)`), so nobody answers
twice, re-read with the board's three-second watch.

**Accept** and **Deny** close the question at once: the card stays dim with the question struck
through, no buttons, the stamp and the delivery line under it, whatever the board file still lists. A
later line on that id changes nothing and is not delivered; a follow-up question takes a new id.
**Update** asks for a check: the question keeps its buttons until the orchestrator rewords or removes
it, and its `✓ update asked` lapses with the orchestrator's next write of the board file (a newer
`updated`). **Read** sends nothing: the item leaves the pane.

### Delivery

The pane sends nothing itself. One deliverer carries every answer line: the board module in the
orchestrator's session, the one whose name equals `updated_by` (found by matching its session id
against `claude agents --json`). It runs from session start, pane open or not, every three seconds,
and at once after a press in that session. Per line it writes one row per recipient to
`board-deliveries.jsonl` beside the answers file (through `hooks/board/deliveries.py`, append-only):

```json
{"id": "Q1", "answer_ts": "2026-11-03T16:00:01.000Z", "to": "lead", "role": "asker", "click_ts": "2026-11-03T16:00:01.000Z", "ts": "2026-11-03T16:00:03.000Z", "delivered": true}
```

| Recipient (`role`) | When | Carrier | Delivered when |
|---|---|---|---|
| `coordinator` (the orchestrator) | always, unless the line came from its own chat (`via: chat`, `session` = the orchestrator) | a prompt as if typed: `<id>: proposal accepted`, `<id>: proposal denied`, `<id>: let's talk about it`, `<id>: I need more information` or `<id>: please check whether this question is still current and correctly worded (goal still active? needs an update?)`, the owner's words on a line of their own when the line has a `quote` | the session stored the prompt as a user row |
| `asker` (`owner_queue[].session`) | unless the line was written in the asker's own session; a question no longer on the board has none | a message to that session: the same text, for **Update** `check whether <id> is still current and well worded; re-ask it with a new id or withdraw it` | the engine queued it there |
| `route` (the orchestrator) | the asker was not reached | a prompt: `<id>: the owner's answer (<kind>) did not reach <asker> (<reason>); wake that session or route the answer` | as `coordinator` |

The board's optional `answer_prompts` words these texts in the orchestrator's own language, `{id}`
standing for the question's id: `{"accept": "{id}: Vorschlag angenommen"}`; `update_asker` is the
asker's Update text; a kind it leaves out keeps the default.

Outcomes, each a row (readers fold the rows of one `id`, `answer_ts` and `role` to the newest `ts`):

| What happened | Row | The pane under the stamp |
|---|---|---|
| both reached | `delivered: true` per recipient | `→ delivered to <asker> 16:08 UTC` |
| the asker is unknown by that name, carried by two sessions, or stopped | asker `delivered: false` with the engine's reason; the routing prompt | `not delivered, with <orchestrator> (not reachable)`, `(name not unique)` or `(gone)` |
| the asker's session holds the message (a `[Cross-session delivery notice]` naming it, usually another permission mode) | asker `delivered: false, reason: held`; the routing prompt | `not delivered, with <orchestrator> (held)` |
| the orchestrator's prompt is never stored (a turn that started after it ended without it, or 30 s idle) | `reason: resubmitted`, the prompt once more; still none after the next turn: `delivered: false` and a toast there | `not delivered, with <orchestrator> (not stored after a resubmit)` |
| the orchestrator's session is not running | a pane whose live column names it gone writes `delivered: false, reason: coordinator not running` for an answer a minute old with no row; the deliverer delivers it once it runs, its newer row replacing the marker | `not delivered, with <orchestrator> (not running)` |

On start the deliverer reads the ledger first: a key with a verdict is never sent again, a key with
no row or only a marker or resubmit is. So after a restart it carries every line that arrived while
it was down. Its first start ever writes one row `{"epoch": "<ts>"}` and carries only lines newer
than that; older lines, hand-written ones included, are never sent. Lines with a kind outside the
five (older hand-written lines with `decided` or a sentence) are read without error and never sent;
the pane shows the last known answer instead. A failed ledger write is logged and the line is
carried again on the next pass.

### Answers given in a chat

When the owner answers a question in a session's chat instead of the pane, that session writes it
back, and the deliverer carries it like a press:

```bash
python3 <plugin>/scripts/board.py answer Q1 accept --session lead --via chat --quote "go ahead"
```

It refuses, writing nothing, an id in neither `owner_queue` nor `news`, an id an Accept or Deny
closed, and a kind outside `accept`, `deny`, `discuss`, `info`, `update`; it opens `board.json`
read-only and prints the line it wrote. `--board FILE` names another board file. Without that line
the question stays open on the pane.

## The freeze flag

`board.py freeze --reason "<why>" [--repo OWNER/REPO ...]` stops every merge: it writes
`freeze.json` beside the board file (`since`, `by`, `reason`, `repos`, `disarmed`,
`not_disarmed`), then disarms every open PR with auto-merge armed in the named repos (default: the
current directory's) and records each one. While the file stands, the merge hook
(`hooks/automerge_gate.py`) refuses every merge and arm in every repo, naming the reason; a file
that does not parse counts as standing. `board.py unfreeze` removes it and prints the disarmed PRs
to re-arm by hand through the hook; it re-arms none itself, so no PR comes back unchecked. The
flag is a brake against slips, not a boundary: any session can delete it
(`scripts/board_freeze.py`).

## The live column

Every minute `hooks/board/probe.py` runs `claude agents --json` and reads, per running session,
only the facts a verdict needs: busy, waiting, blocked, idle or gone; the `WE_ROLE` environment
variable as `master`, `worker` or `other`; the claude-swap profile's folder name from
`CLAUDE_CONFIG_DIR`; and the newest permission mode in the session's transcript. Of a process's
environment it looks at those two keys alone and prints neither value as read. A session that runs
but is not on the board is named in one line below the board.

The second `●` in a master's title is the start mode, with the permission mode as its label; a
worker's line shows the lamp alone. A red or yellow lamp names its reason on the next line:

| Lamp | When |
|---|---|
| red | with `masterProfile` set: a master without `WE_ROLE=master`, or a worker inside that profile |
| yellow | the permission mode differs from the one most running sessions use |
| green | none of the above |

`masterProfile` is a plugin option naming the account folder master sessions run in, with or
without claude-swap's number (`me_example.com` matches `3-me_example.com`); a master runs there pinned or
outside it on the global login (`/we:pin`). Left empty, the two
red rules are off and only the yellow one holds.

## Requirements

Claude Code 2.1.312 or later for the deliverer: the module's tests pass on that build's own engine,
and the carriers were measured live with two background sessions (which run the background
service's build, 2.1.317): `$.session.send` answered `isDelivered: true` for a running session and
`isDelivered: false` with the engine's reason for an unknown name (`No agent named '<name>' is
reachable.`), a name two sessions carry (`2 agents are named '<name>'. Re-send with the ref of the
one you mean: …`) and a stopped session (the unknown-name reason, or right after the stop `Failed to
send to <name>: HTTP 409 — that Remote Control session may have ended or disconnected. …`); a plugin's `$.prompt.submit({
asUser: true })` came back as a `session.append` user row (door `prompt`, origin `plugin`) with the
exact text. Background sessions never held a message, whatever their permission modes, so the held
notice's wording (`hooks/board/fixtures/delivery-notice.txt`) is taken from the build's own strings,
not from a live hold. Below the floor the pane still draws, a toast and a log line say `board:
delivery needs Claude Code ≥ 2.1.312, this is <version>`, and nothing is delivered.

For the live column `python3`, Linux (`/proc`) and `claude agents`; for the work trees `git` and
`gh` signed in. The pane is part of the plugin's hooks module (`we/hooks/board/`, the delivery logic
in `deliver.ts`, the plan reader it shares with `/flow` in `we/hooks/plans/`); `answer.py` appends
the answers, `deliveries.py` the ledger rows, `scripts/board.py answer` a chat answer.
