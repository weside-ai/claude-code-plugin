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
│ [ Read ] ⚑ v2.4.1 is tagged, prod still reports          │
│            v2.4.0  today                                 │
│            The rollout hung on a GitHub 502 and was      │
│            restarted; the lead re-tests once it is live. │
│ [ Read ] ◉ Sign the processor agreement in the           │
│            billing dashboard before Friday so the …  2 d │
╰──────────────────────────────────────────────────────────╯
[ ▸ Log (3) ]

[ ▸ Notes ]  older free text, folded to its first line

╭──────────────────────────────────────────────────────────╮
│ Waiting for you (2)                                      │
│                                                          │
│ Q2  9 d  marketing  PROJ-41                              │
│ Storyline S1–S3                                          │
│ [ Deny ] [ Follow-up ] [ Update ]                        │
│                                                          │
│ Q1  today  lead  PROJ-40                                 │
│ Live test AC 16                                          │
│ → tonight                                                │
│ [ Accept ] [ Deny ] [ Follow-up ] [ Update ]             │
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
unread `news` in one frame with the folded **▸ Log** under it (§ News) and, when set, the older `notes` folded to one line. Then one frame with the open questions, oldest first (only they count as waiting), and one frame per
master with its workers inside, each worker on one line cut to the pane. A master whose group neither
runs nor waits (`idle` or `done`, workers too) and a headless worker group at rest fold into the
last line, **+ N idle/other** (with `(k stale)` when k of them are stale), which opens and closes
them; every session running but not on the board is named in a warning line under it. The frame's border takes the master's lamp colour, red when its start mode is red. The frames
sort by that colour: yellow (waits) first, then green (runs), red, and grey (rests or unknown); a red
frame that waits counts as yellow, and within one colour `priority` orders them. The pane
breaks a header line between its parts, never inside a frame, so it stays readable at 60 columns.

## News

`news` is a list of short items for the owner: what happened that the owner wants to know (an RC cut,
prod live, an epic done), what blocks (`gate`) and what the owner must do (`todo`). The coordinator
writes one with `board.py news add --title "<one line>" [--body "<detail>"] [--kind info|gate|todo]`
(at the top, id `N<n>`), the machinery writes `todo` items itself (bundle, staging past its SLA,
signals, and the launcher's supervisor with `board.py news worker --id W-… --title T`: a worker's
stop its starter could not be told, a permission prompt older than 15 minutes; once per id). The
event poller writes a `gate` item the same way (`--kind gate`) for a damage event no running session
received (§ Event lines). `board.py news merged --pr <ref>` (any session; the watcher
`watch-pr-checks.sh` on a merge and `we-worker close` per merged PR of the story call it) adds one
`info` item `R-<repo>-<n>` for a merged PR that changes `.claude/`, `.weside/` or
`.github/workflows/`: the title in fixed words (`rules changed: <repo>#<n> merged (<count> rule
file(s))`), the body the PR's first summary line, the rule paths and its link. Once per PR, also
after the item was read and pruned:

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
| `title` | required, one line, bold; the pane breaks it onto a second line and cuts it at the end of that |
| `body` | optional detail, dimmed and indented under the title; keep it to a few lines |
| `ts` | optional date or ISO timestamp; shown as its age (`today`, `2 d`) |
| `kind` | optional: `info` (`•`, the default), `gate` (`⚑`, something blocks), `todo` (`◉`, the owner must act); another kind draws as `info`, except those below |

The list keeps the file's order, so the orchestrator puts the newest or most urgent first. Each item
carries **Read** in front; a press appends a `read` line to the answers file (§ Answers) and the item
leaves the pane at once; `board.py` drops it from `news` on its next write (§ Pruning). Until then
an item whose newest line is `read` stays hidden. With every item read the frame is gone.

**Not for the owner.** What a session keeps for the record stays out of the frame. Under it,
**▸ Log (n)** folds the board's `log` (newest first, twenty lines when open, no buttons): a
`decision` (§ Questions and decisions), a `sample` (§ Acceptance), an `escalation` item (the role
holder's signal, § Escalations; the owner's stage is a `todo`, which stands in the frame), and an
older `news` item without an `id`. `board.py` writes decisions and samples to `log` itself, and every write
moves such items, and any `news` item without an `id`, from `news` into `log`, keeping the newest 50
(`tidy_news`, `LOG_KEEP`). A question the cold reader returned (`returned to <asker>: …`) is its
asker's: the refusal and the line's `note` carry it, the owner's news never; an older `returned` item
shows nowhere and goes on the next write (§ Pruning).

`notes` as one string works too: it folds to **▸ Notes** and its first line, dimmed,
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

## Refresh

**Refresh** (hotkey `r`) re-reads the board file, the answers file, the ledger and the live column, and
derives every open work tree with a fresh fetch. It also asks the coordinator to rebuild the board: one
line `{"id": "rebuild", "answer": "rebuild", ts, session}` in the answers file, which the deliverer
carries like an answer (§ Delivery): by prompt into the coordinator's session (at once when the pane
runs there), with its ledger row, resubmit and refusal. The prompt is the board's
`answer_prompts.rebuild`, else `Rebuild the board: check the session lines, the open questions and
the news against the ticketing system, git and the PRs, and correct every stale line (board.py set
--for, withdraw, prune)`, followed by `(Refresh pressed on the board pane in <session>)`. A press
writes no line while an earlier request is still owed, newer than the ledger's epoch and without a
verdict on its coordinator row, so a coordinator that is busy or not running gets one request, not
one per press; a stored or refused request lets the next press ask again. Before the deliverer's
first start (no epoch) requests stay ten minutes apart (`rebuildWaits`, `REBUILD_MS` in
`deliver.ts`). Without a coordinator a press writes none.
Opening the pane re-reads without asking.

## Opening it

`/board` opens the pane; the flow pane's **Board** button does the same, and the board's **Flow**
button opens `/flow`: first its section **Crew flow** (who works, who waits on whom since when, CI
queue and run per open PR, stories waiting on acceptance, every gap, and the swimlane page's path),
read from the last snapshot of `scripts/flow_intervals.py --snapshot` with its age shown; a snapshot
older than 5 min starts one refresh in the background. Below it come the story lights for what this
session works on, when the session names a key. The board's **Zentrale** button opens the
command centre in six sections: **With the owner**, **Red**, **Waiting**, **Working**, **CI** and
**Accounts**. It renders `scripts/command_center/zentrale.py --json`; that script's docstring owns
what each section holds, its sources, thresholds and `schema_version`, and `open_ends.py` owns the
row contract. **Swimlanes** draws `scripts/flow_intervals.py --json` as one lane per session (keys
`1` and `2`: 8 h and 24 h); **Sections** returns. Below the title the pane names the web view: the
link from the crew's `zentrale.web_url` (none while it is unset) and whether `we-crewd` answers on
this host (`scripts/command_center/crewd.py probe`). `we-crewd` serves the same document and the
flow page read-only, for a browser or a phone behind the network's own gate; its docstring owns the
bind rule, the field allowlist, the redaction and the headers, and a launcher of the host starts it
with `crewd.py serve --bind "$(crewd.py pod-ip)"`. Until `/board` runs in a session the pane polls
nothing; the deliverer (§ Answers) checks the board file every three seconds in every session, pane or not, and acts only in the orchestrator's. Once open, the pane checks the file's modification time every three seconds and re-reads it
when it moved; every minute it re-reads the file and the live column whatever happened.

The option `boardAutoOpen` (`/plugin` → we → Configure) opens it at session start: `off` (default),
`on` (every session), `orchestrator` (only the session whose companion pin holds `roles.coordinator`
in the repo's crew, checked by `scripts/crew.py is-role coordinator`; crew file:
`references/companion-session.md` § Crew); a session `wclaude --start` started (`WE_START=1`) opens
it whatever the option. Opened unasked, the pane needs 144 terminal columns and waits
undrawn below that until you widen the terminal or run `/board`.

## The file

**One folder per crew.** A crew's state directory (`crew.py state-dir`) is `WE_STATE_DIR` when set,
else the crew's `state_dir` (a `~` path or one relative to the crew file in the repo's main worktree, so every worktree shares it), else `~/.claude/we-state`.
In a repo with a crew the board is the crew's `board.file` when it names one (relative to the crew
file), else `<state dir>/board.json`; the board's logs, its crew stamp and
`l0-served.jsonl` sit in that folder. A second crew on the same machine sets `state_dir` to a folder of
its own and moves an older shared board there once with `scripts/state_move.py` (dry run, then
`--apply` while none of its sessions runs; the sources stay as `<name>.migrated-<date>`). A session
without a crew reads the plugin option `boardFile` (`~/` and a relative path count from the home
folder), else `~/.claude/we-state/board.json`; the option never beats a crew. `board.py` without
`--board` writes the crew's board; `board.py path` prints it, `--crew-only` only when it is not the
default board. Without the file the pane says so and points here.

**Crew guard.** Each board carries the crew that owns it in a stamp beside it (`crew.id` for
`board.json`, `<stem>-crew.id` otherwise), left by the first write of that crew to its own board. A
writing `board.py` verb refuses (exit 3, naming both crews and `--board`) when the session's crew is
not the board's: a session without a crew (no crew file, an unreadable one, or a pin
`WESIDE_COMPANION` that is no member of the cwd's crew) on the default board, or any session on a
board stamped for another crew. `path`, `check`, `escalation list` and `escalation count` only read
and pass. An explicit `--board` on an
unstamped file passes. The role hook names a state directory another crew holds (one line, with the
fix) and a plugin older than the user install that a project-scope install keeps in place.

**Logs per board.** Every JSONL file beside the board carries the board file's stem: `board.json`
keeps `board-answers.jsonl`, `board-questions.jsonl` and the rest; `acme-board.json` writes
`acme-board-answers.jsonl` and so on, and counts its `Q`/`D`/`E` ids on its own. Below, the
names are those of the default board.

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
| `updated` | ISO timestamp of the last write; `board.py` stamps it on every write of the coordinator (a worker's `set` leaves it); the header shows its age, yellow from 2 h, red from 8 h |
| `updated_by` | who wrote it, shown beside the age |
| `answer_prompts` | optional `accept`, `accept_hand`, `accept_task`, `deny`, `followup`, `followup_route`, `update`, `withdraw`, `update_asker` and `rebuild` texts the deliverer sends (§ Answers, § Refresh) |
| `priorities` | a list or one string; the pane shows it as one dimmed line under the header, a list joined with ` · ` |
| `news[]` | optional: short items for the owner with `id`, `title`, `body`, `ts`, `kind`, each with a **Read** button (§ News); `board.py` writes `info`, `gate` and `todo` (`news add`; a rules line `R-<repo>-<n>` by `news merged`; the bundle, an escalation at stage `bundle`, a signal `S<n>` with `for` the role and `key`, § Several humans; staging past its SLA) and `escalation` (a record at stage `escalation`, with `for` the role waited on, shown in the log) |
| `log[]` | optional, written by `board.py`: entries kept for the record (`decision`, `sample`, older news without an id), the newest 50; the pane folds them under the news (§ News) |
| `notes` | optional, older: one free text, folded under the news to its first line (§ News) |
| `staging` | optional, written by `board.py staging`, `book` and `unbook` only: `synced`, `repo`, `sla_hours`, `booking` (`issue`, `holder`, `until`) and `acceptance` (`issue`, `rc`, `opened`, `due`, `keys`, `past_sla`, `news`), each `null` when none is open; the pane draws one `◇ Staging` line per open one, a booking past its `until` as expired, and the past-SLA mark with the block's `sla_hours` (§ Staging) |
| `owner_queue[]` | questions only the owner can answer, oldest `since` (YYYY-MM-DD) first, its age in days yellow from 2, red from 7 |
| `owner_queue[].id` | the question's id; without one the row has no answer buttons |
| `owner_queue[].session`, `.key`, `.ask`, `.recommendation` | who asks, the ticket, the question, the asker's recommendation; **Accept** shows only with a recommendation, **Deny** always |
| `owner_queue[].to`, `.to_name`, `.label` | optional: a question `board.py ask --to` sent to a human on another machine, that human's name and the ticket label it carries (§ Several humans); its answer comes from the ticket, so the card shows `waiting on <to_name> (label <label>)` and only **Withdraw** |
| `owner_queue[].key_title`, `.cause`, `.ts` | the ticket's title, why the owner is asked (`merge-go`, `plan`, `prod`, `cut-fence`, `access-click`, `window-go`, `info`; a `window-go` is a go the owner must type in the asking session's own window, its `ask` naming that window and the exact sentence) and when it was posted (ISO UTC); `board.py ask` writes all three |
| `owner_queue[].pr_url`, `.one_way` | the open PR a `merge-go` question is about and its one-way class (`board.py ask --pr`, `--one-way`); with both, the card shows `merge go (<class>): <url>` and names **Accept** **Go** (it writes `accept`, the owner's go: the deliverer sends `accept_hand`, § Answers, and the asking session arms the PR with `arm_pr.sh <PR>`), and `board.py close-merged` drops an open one once the PR is merged or closed |
| `owner_queue[].kind`, `.source`, `.owner` | `task` (`board.py ask --kind task`: the card offers **Taken** in place of **Accept** and stamps `taken`; the deliverer sends `accept_task`, § Answers); where the ask's fact comes from (`--source`, shown dimmed under the ask); the member who owns the subject (`--owner`, or `--component` resolved through the crew's `members.*.components`): the deliverer sends that session a copy of every answer (§ Answers) |
| `owner_queue[].urgent`, `.obsolete` | `true` for a question asked `--urgent` (listed first in the bundle); the reason a question became moot (`board.py blocked --clear`, § Blocked workers) |
| `sessions[].name` | the session's name as `claude agents` lists it; the live column matches on it |
| `sessions[].role` | `master` or `worker`; a session other sessions name as `parent` counts as a master |
| `sessions[].parent` | the master a worker reports to; workers are listed under it |
| `sessions[].state` | `build`, `ci` or `active` (● runs), `wait-owner` (◉ waits, listed first), `idle`, `parked` or `done` (○ rests); anything else `?`. `board.py`'s `SESSION_STATES` owns this list; the pane draws `active` and `parked` as `?` until its lamps follow |
| `sessions[].since` | `YYYY-MM-DDTHH:MMZ`: in this state since; a wait (`waiting_on`) is such a state, so `board.py set waiting_on=…` moves it |
| `sessions[].waiting_on`, `.sla_due` | the role key (or `human`) the session waits on, and when that wait passes the SLA (`YYYY-MM-DDTHH:MMZ`, the crew's `sla.hours` counted only inside `sla.daytime` in `sla.tz`); written by `board.py set` and, for a blocked worker, `board.py blocked` only (§ Questions and decisions) |
| `sessions[].blocked` | a worker waiting on a permission prompt or on a reply: `kind`, `starter`, `starter_session_id`, `key`, `since`, `waiting_for`, `command` (§ Blocked workers) |
| `sessions[].updated_at` | `YYYY-MM-DDTHH:MMZ`: when the line was last written; `board.py set` stamps it, a hand write should too. The pane shows the line's age (this, else `since`) beside its lamps: dim while fresh, grey from 6 h, red and marked `stale` from 24 h; a stale line folded into **+ N idle/other** is counted on that button (`(1 stale)`), never hidden without a trace |
| `session_age_hours` | optional `{"grey": 6, "stale": 24}`: moves both age thresholds (board.ts `SESSION_AGE_HOURS`); a pair that is not `0 < grey < stale` is ignored |
| `sessions[].priority` | a number, lower first; sessions without one after those with one; shown as `P<n>` in the title, or before `direction` |
| `sessions[].cwd`, `.session_id` | optional, never shown: the directory the session runs in and its Claude Code session id, so the orchestrator keeps the list of its masters and can restore one after a workspace crash in the right directory with `claude --resume <session_id>`; a master's `cwd` is also the repo its work tree is read from (§ Work) |
| `sessions[].work` | optional: a master's ready work tree, which replaces the derived one (§ Work) |
| `companion`, `keys`, `topic`, `now`, `pr`, `direction`, `note` | shown as written: name in brackets, ticket keys, topic (dimmed), current step, PR number, `P<priority> · direction`, a warning line; a worker shows lamp, name, keys, PR, live status, start lamp and `now` on one line |

Every field but `sessions[].name` may be missing or `null`; the pane leaves it out.

## Answers

Each question with an `id` carries the buttons **Accept** (only with a `recommendation`; **Go** on a
one-way merge question), **Deny**, **Follow-up** and **Update**; a question
sent to a human on another machine (`to`) carries only **Withdraw**; each news item carries **Read**. A press appends one line to `board-answers.jsonl` in the board
file's folder (default `~/.claude/we-state/board-answers.jsonl`) and never writes `board.json`, so
an `owner_queue` item keeps no answer: `board.py show <Q>` prints the question with its answer lines
and its status, the read before any session repeats it or writes the same answer again:

```json
{"id": "Q1", "answer": "accept", "ts": "2026-10-30T17:12:00.000Z", "session": "Orchestrator"}
```

| Field | Meaning |
|---|---|
| `id` | the question's `owner_queue[].id`, or the item's `news[].id` |
| `answer` | `accept`, `deny`, `followup`, `update` or `withdraw` for a question; `read` for a news item; `rebuild` for Refresh's request (id `rebuild`, § Refresh) |
| `ts` | when it was pressed, ISO UTC |
| `session` | the name of the session the line was written in, as `claude agents` lists it; `null` when the live column does not know it |
| `ask`, `recommendation` | the open question's ask and recommendation, verbatim, on a line `board.py` wrote; a pane line takes them from the board item when it is delivered |
| `via`, `quote` | only on a line `board.py answer` wrote (`chat`, and the owner's own words when given) or `board.py signals` read from a ticket (`ticket`, and the reply; § Several humans) |

The file only grows (`answer.py` and `board.py` append with `O_APPEND`, nothing rewrites it);
`board.py` removes the question from `owner_queue`, or the item from `news`, once handled (§ Pruning). The pane
shows the newest answer beside the question (`✓ accepted 18:12 UTC (Orchestrator)`), so nobody answers
twice, re-read with the board's three-second watch.

**Accept**, **Deny** and **Withdraw** close the question at once: the card stays dim with the question struck
through, no buttons, the stamp and the delivery line under it, below the open questions for ten minutes
after the answer (`STRUCK_SHOWN_MS`); after that the pane hides it unless its answer is still
undelivered (the stuck answers), whatever the board file still lists,
and the next board write drops it once its asker has the answer (§ Pruning). A
later line on that id changes nothing and is not delivered; a follow-up question takes a new id.
**Update** asks for a check: the question keeps its buttons until the orchestrator rewords or removes
it, and its `✓ update asked` lapses with the orchestrator's next write of the board file (a newer
`updated`). **Withdraw** goes to the asker as `<id>: withdrawn on the board; take its label off the
ticket and say so in one comment there`. **Read** sends nothing: the item leaves the pane.

### Delivery

The pane sends nothing itself. Questions are posted by their asker; the coordinator delivers and
tidies, it is no post office. One deliverer carries every answer line: the board module in the
orchestrator's session, the one whose name equals `updated_by`, or, while that field is empty (a
`board.py` write never sets it), the crew's coordinator (`roles.coordinator` in the crew file of the
session's repo, read once at session start, and only when the board is that crew's `board.file`); found by matching its session id against
`claude agents --json`. It runs from session start, pane open or not, every three seconds, and at
once after a press in that session. The pane says it in red above the queue when neither names a
coordinator, and when a press (a line without `via`) has had no verdict from any recipient for five
minutes. Per line it writes one row per recipient to
`board-deliveries.jsonl` beside the answers file (through `hooks/board/deliveries.py`, append-only):

```json
{"id": "Q1", "answer_ts": "2026-11-03T16:00:01.000Z", "to": "lead", "role": "asker", "click_ts": "2026-11-03T16:00:01.000Z", "ts": "2026-11-03T16:00:03.000Z", "delivered": true}
```

| Recipient (`role`) | When | Carrier | Delivered when |
|---|---|---|---|
| `coordinator` (the orchestrator) | always, unless the line came from its own chat (`via: chat`, `session` = the orchestrator) | a prompt as if typed: `<id>: proposal accepted` (an Accept on a one-way `merge-go` with its PR, **Go**: ``<id>: the owner's go on <pr_url> — the asking session arms that PR with `arm_pr.sh`; `board.py show <id>` keeps the go``; **Taken** on a task: `<id>: taken — the owner does this task; do not do it yourself`), `<id>: proposal denied`, `<id>: follow-up. Complete the question with what it lacks (options, consequences, recommendation) and offer to talk it over.` or `<id>: please check whether this question is still current and correctly worded (goal still active? needs an update?)`, then where it was written (`(answered from the board pane in <session>)`, `(answered in the chat of <session>)` or `(answered on ticket <KEY> (<human>))` after a space: transparency, no check), then on lines of their own the question (`The question: "<ask>"`), its recommendation (`The recommendation accepted: "…"`, `denied` on a Deny) and the owner's words when the line has a `quote` | the session stored the prompt as a user row |
| `asker` (`owner_queue[].session`) | unless the line was written in the asker's own session, or the asker is the coordinator (its `coordinator` prompt carries the answer, and its delivered row lets `prune` drop the question); a question no longer on the board has none | a message to that session: the same text, for **Update** `check whether <id> is still current and well worded; re-ask it with a new id or withdraw it` | the engine queued it there |
| `owner` (`owner_queue[].owner`) | unless it is the coordinator, the asker or the session that wrote the line | a message to that session: the coordinator's text plus `(copy for the owner of this subject)`; a refusal is a ledger row only, no routing line | the engine queued it there |
| `starter` (`owner_queue[].starter`) | only on a question with `answer_to: asker`, once the asker refused or was not reached | a message to the asker's starter: the asker's text plus `(for <asker>, which did not take it: carry it on or act on it)` | the engine queued it there |
| `route` (the orchestrator) | the asker was not reached (with `answer_to: asker` and a starter: the starter was not reached either) | a prompt: `<id>: the owner's answer (<kind>) did not reach <asker> (<reason>); wake that session or route the answer` | as `coordinator` |
| `route` on a Follow-up (the orchestrator) | on a question with `answer_to: asker`, once the starter took a Follow-up the asker did not | a prompt: `followup_route` naming the starter, `<id>: Follow-up → tell the owner in one line: talk to <starter> (<cwd>). Do not answer or relay it yourself.` | as `coordinator` |

**`board.answer_to`** decides who carries an answer: `asker`, the default, or `coordinator`, the
opt-out. The crew file's value beats the asking repo's `.weside/config.json`, so a companion asks
the same way from any repo. `board.py ask` stamps the question with `asker_id` (the
asking session's id) and the launcher marker's `starter`, both only when `--session` is the
caller itself, and, under `asker`, `answer_to: asker`. On
such a question the asker gets the answer as above and the coordinator's prompt is one copy line,
`<id>: <kind> — copy for the queue; the answer goes to <asker> directly, do not relay it` with the
writer note; an asker that is gone hands it to its starter (role `starter`), and only when that
fails too does the coordinator get the routing line. A **Follow-up** on such a question sends the
asker the `followup` text (complete the question with what it lacks and offer to talk it over, the
starter the same text when the asker is gone) and the coordinator `followup_route` in place of the
copy line (`<id>: Follow-up → tell the owner in one line: talk to <asker> (<cwd>). Do not answer or
relay it yourself.`, the window from the asker's board line `cwd`); when the starter took it, a
second `followup_route` names the starter. Without a starter the `followup_route` waits
for the asker's delivery: an asker not reached leaves only the routing line. A question without the
stamp keeps the coordinator's full text.

The board's optional `answer_prompts` words these texts in the orchestrator's own language, `{id}`
standing for the question's id, `{pr}` for its PR link and `{who}` for the session a `followup_route` names: `{"accept": "{id}: Vorschlag angenommen"}`;
`update_asker` is the asker's Update text, `accept_hand` (the go on a one-way PR, armed by the
asking session) and `accept_task` (the owner does it) the two Accepts with a meaning of their own
(never `accept`'s text); a kind it leaves out keeps the default. A key that names no kind here (an older `discuss` or `info`) is ignored, and the deliverer skips an answers line of such a kind.

Outcomes, each a row (readers fold the rows of one `id`, `answer_ts` and `role` to the newest `ts`):

| What happened | Row | The pane under the stamp |
|---|---|---|
| both reached | `delivered: true` per recipient | `→ delivered to <asker> 16:08 UTC` |
| the asker is unknown by that name, carried by two sessions, or stopped | asker `delivered: false` with the engine's reason; the routing prompt | `not delivered, with <orchestrator> (not reachable)`, `(name not unique)` or `(gone)` |
| the asker's session holds the message (a `[Cross-session delivery notice]` naming it, usually another permission mode) | asker `delivered: false, reason: held`; the routing prompt | `not delivered, with <orchestrator> (held)` |
| the orchestrator's prompt is never stored (30 s idle after it; a turn that ends meanwhile is no miss, the prompt may be queued behind it) | `reason: resubmitted`, the prompt once more; still none after another 30 s idle: `delivered: false` and a toast there | `not delivered, with <orchestrator> (not stored after a resubmit)` |
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

`--text-file <path>` (or `-` for stdin) takes the owner's words in place of `--quote`, so a code
span in them never meets the shell.

It refuses, writing nothing, an id in neither `owner_queue` nor `news` and a kind outside `accept`,
`deny`, `followup`, `update`, `withdraw` (the human's take-back of an `ask --to` question,
which closes it like Accept or Deny); it opens `board.json` read-only and prints the line it wrote. A
second answer on an id an Accept or Deny already closed (the owner answered twice) is a duplicate:
no answer line, so nothing is carried again, one `duplicate-answer` line in `board-questions.jsonl`,
and exit 0 with `<id> is closed by <kind>; recorded as a duplicate, nothing runs again`. `--board FILE` names another board file. Without that line
the question stays open on the pane.

**The go comment.** An Accept on a one-way `merge-go` question that carries a Codex finding posts
one PR comment through `gh` (the session's GitHub identity), from either answer path (`answer.py`
`post_go`: the pane's press and `board.py answer`). Its first line is exactly
`<!-- board-go Q<n> head=<the question's 40-hex head sha> -->`, then the owner's answer quoted (the
chat's `--quote`, else `Go (Accept on the board)`), the finding and the asking session's reason. A
CI job counts that marker on the PR's current head as the skip; a question superseded by a new head
never reaches it. The marker records the answer the board holds; it is no proof of who gave it, since
any session with the same identity could post the line (the crew does not guard against its own
sessions, so a job reads it only from the bot identity and only on the current head). Each post leaves one `go-comment` line (`ok`, `pr`, `head`, `url` or `error`) in
`board-questions.jsonl`. A failed post is never silent: the answer line stands, `answer.py` exits 3
and the pane shows a toast, `board.py answer` exits 3 with the reason on stderr; the same Accept
again (`board.py answer <id> accept --session <name> --via chat`) posts it, also after the question
left the board, and a posted comment is never posted twice.

## Questions and decisions

`board.py` (in the plugin's `scripts/`) writes `board.json` only through one locked writer: an
exclusive lock on `board.json.lock` beside it (10 s, then it gives up naming the file), a fresh
read, then a temp file and `os.replace`. A hand write between that read and the replace is lost.
The JSONL files beside the board only grow (`O_APPEND`, one whole line per write). A line that
records a board change is appended after board.json was replaced, still under the lock, so a failed
write leaves no line.

A refused value prints the valid values and one line `corrected call: board.py …` with the value
it likely meant (`state=working` → `state=build`, a member's name in `waiting_on` → the role it
holds, a field passed as a flag `--now x` → `now=x`, an answer kind `no` → `deny`).

**`set` — the session's own line.** `board.py set now="<step>" state=<state> waiting_on=<role>`
writes the line whose `name` is the caller's, as `claude agents --json` lists it for its
`CLAUDE_CODE_SESSION_ID` (a missing line is appended with `name` and `session_id`; a session without
a name is told to `/rename` first; `--session <name>` is only checked against that name). Only `waiting_on`, `state`, `now`, `topic` (one line), `keys` (comma-separated, each a match of
`naming.key`; an empty value clears it) and `epic` (a ticket key or an epic number, read by
`scripts/epic_state.py`) and `wake` (one line: the checkable trigger that wakes a parked session) are settable; `state` takes
the values of `sessions[].state` above, `waiting_on` a role key or `human`. `--for <name>` writes
another session's line and is the coordinator's (`roles.coordinator`). A new `waiting_on` stamps
`since` and `sla_due`; the same role keeps both; another role resets them; `waiting_on=` on a waiting
line clears all three and on any other line changes nothing, so a hand-written `since` survives.
`state` and `now` never touch `since`; every `board.py` write of the coordinator stamps `updated`, none writes `updated_by`.

**`ask` — a question for the owner.** Any crew session asks its own question with `board.py ask`,
whatever its role; a worker asks its starter, which posts it. The coordinator keeps the queue tidy
and carries only what the deliverer could not deliver. The call is
`board.py ask --key <KEY> --key-title "<title>" --ask "<question>"
--recommendation "<recommendation>" --cause <cause>`; `--session <asker>` defaults to the session's
own name as `set` finds it. `--text-file <path>` (or `-` with a quoted heredoc on stdin) takes the
question in place of `--ask`: inside double quotes the shell runs a `code span` and leaves an empty
gap, and a refusal whose text shows such a gap names `--text-file`. A missing or blank field, a key outside the
crew's `naming.key` or a cause outside the six is refused, one line each, before anything runs.
A `merge-go` question also needs `--pr <ref>` (a URL, `<owner>/<repo>#<n>` or a number) on a PR
`gh pr view` reads as `OPEN`; a merged or closed one is refused before the reader, so no question
asks about a merge that already happened. `--one-way <class>` (merge-go only) marks a one-way PR:
the card offers the link and **Go**: an Accept is the owner's go, and the asking session arms the
PR with `arm_pr.sh <PR>` (no approve on GitHub is the go). The helper reads no board: it names the
one-way class on its output and on the PR, and refuses the class only to a worker. The item keeps the
PR's head sha (`head`). A one-way PR has one open question: a second one-way ask on the same PR is
refused naming the open one, and `--supersede` (a new head) posts it and takes every open one-way
question on that PR off the queue, each with a `superseded` line naming the new id in `by`, so the
owner's yes only ever meets the newest head. `--codex-finding <text or link>` with `--codex-reason
<text>` (one-way only, both or neither) names a Codex finding the asking session skips: the ask gets
the line `On yes the Codex finding counts as skipped: <finding> (reason: <reason>)`, and the owner's
Accept counts as that skip (§ Answers, the go comment). `board.py close-merged`
(also run by `bundle` and `/we:merged`) removes every merge question still in `owner_queue` whose
PR merged or closed, whatever its answer (a Go, the owner's hand merge) and in whichever repo
its `pr_url` points, logs one `closed` line each in `board-questions.jsonl` and prints
`closed <id>: PR <state> <url>` per question.
Then a cold reader judges the question: one `claude -p` run (the prompt, model and effort of
`templates/cold-reader.md`) in an empty directory, with no tools, no MCP server, no settings files, hooks
off, no session file and the global login, given only the question (the asker's own text: the required-checks line a
merge-go appends reaches the owner, never the reader), the recommendation, the title
and the crew's two labels. It must say what the owner decides and what happens on yes, and it names
form findings: more than one decision, no recommendation, more than three options, another
language than the labels. A question that passes lands in `owner_queue` as `Q<n>` (one above every
`Q` number on the board, in the answers file and in the log), with `since` and `ts` stamped by the
script, and prints exactly one JSON object on stdout, `{"id": "Q<n>", "outcome": "posted"}` (an
`ask --to` on jira adds its `carry` list; everything else goes to stderr). The same question again
from the same session within an hour (same text, key, cause, recommendation and `--to`, no
`--replace`) while the first is still open posts nothing: it prints the first id with
`"outcome": "repeat"` and logs a `repeat` line, so a retry never doubles a question; a re-ask
after a withdraw or an answer posts anew. One that does not comes back, never silently: exit 1 with
`returned to <asker>: <reason>`, the same text as the asker's line's `note`; the owner's news gets
nothing. The asker's next posted question clears a `returned to` note; a note that does not start
with `returned to` is never overwritten, and the refusal and the `returned` line in
`board-questions.jsonl` alone carry the return. A reader that cannot run (no `claude`, 90 s, no parseable
answer) never holds a question back: it is posted unread, stderr says `reader-error: <cause>; posted unread`.

**One open question per key and cause.** An `ask` on a key that already has an open question
with the same cause, PR and `--to` human is refused as a `duplicate` (a line in
`board-questions.jsonl`, naming the open id); `--distinct` posts it anyway when it is another
question. Another open question on the key draws one stderr warning. `--replace <Q>` replaces the
asker's open question `<Q>` on the same `--key`: once the new one is posted, `<Q>` leaves
`owner_queue` and gets a `replaced` line with `by` the new id; an id that is not open, or open on
another key, is refused. An asker who takes a question back without a new one runs
`board.py withdraw <Q>` (§ Several humans).

**An answer worth keeping** is written where the next agent works (`references/code-notes.md`), by
the asker, in the commit it makes anyway: the board is pruned, the code stays.

Every `ask` past the field check appends one line to `board-questions.jsonl`:
`{id?, ts, session, key, key_title, ask, recommendation, cause, outcome, reason?, reader?}`, with
`outcome` `posted` (only then `id`), `returned`, `duplicate` (with `of`), `replaced` (with `by`), `repeat` (with the first `id`), `closed` (`close-merged`) or `pruned` (§ Pruning), and `reader` the reader's raw
`decides`, `on_yes`, `form`. A duplicate answer adds a `duplicate-answer` line (§ Answers given in a
chat). The line keeps the question's text after it leaves `owner_queue` (§ Pruning, `close-merged`), so
questions per day and answer times come from this log joined with `board-answers.jsonl` by `id`.
`--urgent` adds `urgent: true` to the item and to its log line; the urgency changes only the order
in `bundle`, never whether the question goes out.

**Waits log.** Whenever a line's `waiting_on` ends or changes (`set`, `blocked`), one row
`{key, session, waiting_on, since, ended, duration_s}` is appended to `board-waits.jsonl` after
board.json was replaced: `key` is the line's first `keys` entry, its `blocked.key`, else the first
`naming.key` match in its name, else null. It is the source of waits by role in the weekly flow
report.

**`log correction` — the human corrected a session.** `board.py log correction <session> <kind>`
is the coordinator's: one line `{type: "correction", ts, session, kind, by}` in the flow log
(`scripts/flow_log.py` owns its path `<flow.log_dir>/sampler-<day>.jsonl` and its line schema).
`kind` is one lower-case token; another role, another kind or an unset `flow.log_dir` is refused and
nothing is written.

### Pruning

Handled entries leave `board.json` without a hand edit. Every `board.py` write runs one pass under
the board lock (`prune` in `board.py`), and `board.py prune` runs it alone and prints the ids:

| Entry | Leaves when |
|---|---|
| a question (or item) an Accept or Deny closed | nothing is owed to its asker any more, since the deliverer finds the asker only on the board: each answer line on the id is older than the ledger's `epoch`, written in the asker's own session, or has an asker row `delivered: true` in `board-deliveries.jsonl` (refused, or not taken 24 h after the answer: a delivered `starter` or `route` row, which the deliverer writes to the coordinator then, `ROUTE_AFTER_MS` in `deliver.ts`). A close no one carried stays however old, a `duplicate-answer` line changes nothing, and a **Go** on a one-way merge-go or an Accept on a `window-go` leaves like any other close: the asker holds the go in its prompt and in `board.py show`, the owner's queue keeps only what waits for the owner |
| a question its asker took back, unanswered | a `withdrawn` or `superseded` line names it (`board.py withdraw`, `supersede`; § Several humans) |
| a news item | its newest answer line is `read` |
| a `returned` item | at once (reason `returned`): its asker has it |
| a bundle `B-<date>` | 24 h after its `ts` (`PRUNE_AFTER_H`) |
| an escalation item `E<n>`, `E<n>a` | never: `escalation settle` drops it |

Follow-up and Update keep a question. Each drop appends one line
`{id, ts, outcome: "pruned", field, reason, answer?}` to `board-questions.jsonl`
(`reason` `answered`, `withdrawn`, `read`, `returned` or `expired`), so a dropped id is never handed out again. Leftovers from before the pass go on the
first write after the update.

### Blocked workers

A sampler outside every session (it holds no crew role) polls `claude agents --json` and marks a
worker that sits on a permission prompt or idles on a question with `board.py blocked`. The verb is
its own brake: it re-reads `claude agents --json` and refuses (exit 1, nothing written) unless the
named session is blocked on a permission prompt right now (`--kind permission`) or idle right now
(`--kind chat`), so a forged call writes nothing for a session that is not waiting.

| Call | Writes on the session's line |
|---|---|
| `blocked <name> --kind permission [--starter S] [--key K] [--command T]` | `waiting_on: human`, `since`, `sla_due`, `blocked` |
| `blocked <name> --kind chat --waiting-on <role\|human> …` | `waiting_on` (a role key or `human`), `since`, `sla_due`, `blocked` |
| `blocked <name> --clear` | removes all four once; refused while the permission prompt still stands (only a permission wait reads `claude agents --json`, once, before the board lock) |

`blocked` is `{kind, starter, starter_session_id, key, since, waiting_for, command}`: `starter` the
session that started the worker and its id from `claude agents --json` (the prompt hook matches on
it), `since` (ISO UTC) the start of the wait, kept while the same kind is called again, so a chat
wait that moves from the starter's role to `human` keeps it; `waiting_for` the permission prompt as
`claude agents` names it; `command` at most 200 characters the caller already filtered for secrets.
A line that is missing is appended with `name` and `session_id`; no other field is written; a
`--key` outside the crew's `naming.key` is refused. The same call again prints
`board.py blocked: <name> unchanged` and writes nothing. A session that sets its own wait with
`set waiting_on=…` ends the old wait and drops its `blocked` mark. The prompt hook
`sampler_on_prompt.py` names a blocked line once per wait to its starter (a `chat` wait also to
the coordinator), the command JSON-quoted and labelled as data; the coordinator hears of an open
permission prompt from the event poller alone (§ Event lines).

`--clear` prints `{cleared, kind, key, since, duration_s, obsolete}`. It marks every open
`owner_queue` question of that session that the wait raised, posted during the wait (cause
`access-click` for a permission wait, `info` for a chat wait), `obsolete: "<labels.prompt_resolved>
<HH:MM>"` (crew time zone): the question stays in the queue, so nobody answers a dead prompt (a
worker its starter answered meanwhile, or one that stopped) and nothing vanishes silently.

**`decision` — an owner's cut, fence or process decision.** `board.py decision <area>
<cut|fence|process> --key <KEY> --text "<decision>"` needs the caller to hold `roles.<area>`; a
decision without a ticket names a plan slug as `--key`, as `ask` does. It writes the `log` entry
`{id: "D<n>", kind: "decision", title: "<area> <kind> <KEY>: <decision>", ts, by}`, then appends
`{id, kind: "decision", title, ts, by, area, decision, key, text}` to `board-decisions.jsonl`.

**`bundle` — the evening bundle.** The coordinator runs `board.py bundle` at its `bundle` cadence.
It writes one news item `B-<YYYY-MM-DD>` (`-2`, `-3` for a further bundle that day) of kind `todo`,
titled `Bundle <date>: <n> decisions · <m> open questions`, its body one line
`<area>: <kind> <KEY> <text>` per decision since the last bundle, grouped by area, then
`open: Q12 (urgent), Q15 …`, the questions no Accept or Deny closed, urgent ones first and oldest
`since` first within each group, then `obsolete: Q9 (<reason>)` for questions whose prompt resolved
(§ Blocked workers), which the coordinator removes from the queue. Then it appends
the marker `{"bundle": "<id>", "ts": …}` to `board-decisions.jsonl`, so the next bundle shows only
newer decisions. With nothing to show it prints `bundle: nothing` and writes nothing. Before it
writes, `bundle` runs `escalation route`; each open record at stage `bundle` adds one line
`escalation E<n> <KEY>: <question>` after the `open:` line (with `(advice pending)` or
`(advice: <text>)` on a `--touches` record), and the title ends in `· <k> escalations`.

## Escalations

`board.py escalation` holds the decision story between two role holders. It
appends events to `board-escalations.jsonl` beside the board (`O_APPEND`, only grows); a record is
the fold of its events by `id` in log order (`fold_escalations`). A party opens one with
`escalation open --key <KEY> --parties <role>,<role> --question "<q>" --a "<option>" --a-cost "<cost>"
--b "<option>" --b-cost "<cost>" --reversible <yes|no> [--touches <topic>]`.

| Event | Who | Fields |
|---|---|---|
| `open` | a holder of one of the two `--parties` roles | `id` `E<n>`, `ts`, `key`, `parties` (two different role keys), `by`, `question`, `a`, `a_cost`, `b`, `b_cost`, `reversible` (bool), `touches` (`vision`, `money`, `law`, `priority` or null), `stage: self`, `waiting_on` (both parties, comma-joined), `since`, `since_open`, `sla_due` |
| `route` | the coordinator (`escalation route`, also inside `bundle`) | `from`, `stage`, `waiting_on`, `since`, `sla_due`, `advice_from` on a `--touches` record |
| `advise` | the `roles.escalation` holder, `--touches` records only | `by`, `recommendation` |
| `settle` | see below | `stage`, `by`, `outcome`; the record is closed |

`since` and `sla_due` are UTC minutes; `sla_due` is the crew's `sla.hours` counted inside
`sla.daytime` in `sla.tz` (`daytime_due`, the arithmetic of `set waiting_on`).

**Stages.** `route` moves only an open record whose `sla_due` has passed:

- `self` → `escalation` (`waiting_on: escalation`) while the `roles.escalation` holder has a board
  line (`sessions[].name` equal to its slug or name) that is not `parked`; `idle` counts as there.
- `self` → `crew.fallback.escalation` when that line is `parked` or missing: a role key gives stage
  `escalation` waiting on that role; `human_bundle` or no fallback gives stage `bundle`.
- `self` with `touches` → `bundle` with `advice_from: escalation`, whatever the holder's line says.
- `escalation` → `bundle` (`waiting_on: human`).

Entering `escalation` adds one `news` item `{id: "E<n>", kind: "escalation", for: <the role waited
on>, title: "Escalation E<n> <KEY>: <question>", body, ts}`; entering `bundle` replaces it by the
same item of kind `todo` without `for` (one item per id). A `--touches` record entering `bundle`
with its advice pending gets a second item beside the todo, `{id: "E<n>a", kind: "escalation",
for: "escalation", title: "Advice E<n> <KEY>: <question>", body, ts}`: the human's todo keeps
`E<n>`, the holder's advice signal takes its own id, so each id still names one item. `advise`
drops `E<n>a`; `settle` drops `E<n>` and `E<n>a`. Every one of these goes through the locked writer,
and the event is appended after it; a failed board write appends none and changes no item. A
record stays in `bundle` until it is settled.

**List.** `escalation list [--waiting-on ROLE] [--stage STAGE]` (read-only) prints one line per open
record waiting on the role, `E<n> <KEY> <role>/<role> <stage> since <since> due <sla_due>`, or
`escalations: none waiting on <roles>`. A `--touches` record with its advice pending also waits on
`escalation` (its `advice_from`) beside `human`, and its line ends in `(advice pending)`. Without `--waiting-on` it lists the records waiting on the
roles the caller holds; a caller holding none is refused.

**Settle.** `escalation settle E<n> --outcome T`: at `self` a party, at `escalation` the holder of the
role in `waiting_on`, at `bundle` only the coordinator with `--via human` (the human answered on
the board item). A `--touches` record refuses `--via human` with `waiting for the escalation role's
recommendation` until `advise` is in. A settled record refuses every further settle.

**Ticket.** With `board.ticketing: jira`, `open` and `settle` print as their last stdout line
`carry: [{"op": "comment", "key": <KEY>, "text": …}]`: the decision story (question, both positions
with their costs, reversibility, wait) or the outcome. The session posts it with its ticketing MCP.

**Count.** `escalation count` prints `<role>/<role> <n> in <YYYY-Www>` per role pair (sorted, so
A/B and B/A count together) over the records opened in this ISO week, and past two
`warning: <pair>: more than two escalations this week; the right in crew.json is drawn wrong`.
`open` prints the same two lines when its record is the third or later of its pair that week.

## Moves

`board.py select` and `board.py move` move a story between the seven states. Each state's entry rule
is the process template's §Lifecycle (`process/L0.md`); this section names only what the script
adds. Every rule runs before any write; a refusal writes no row, calls no adapter and prints no
`carry:` line, and exits 1.

| Verb | Rule as the script checks it | Refusal |
|---|---|---|
| `select <KEY> [--plan PATH] [--refiner]` | `ENTRY_RULES["selected"]`, in order: the plan on `risk.rules_from` after one fetch (default path `docs/plans/<KEY>-story.md` under `git rev-parse --show-toplevel`); with `--refiner` (a refiner selecting its own story) the story's epic plan on that ref, which must be approved (`status:` starting `approved`, the backlog rule's reading), hold the key on its `line:` and carry no `select: owner`, and the crew must not set `select.refiner: false`, else the product role selects (group `refiner`); the Ready gate's story checks on that blob, the plan-only tier, and, unless that tier is `T0` (no panel; the row and comment say `panel none (T0)`), a green `ready-<KEY>` lens verdict whose subject hash is that blob's (an edit of the excluded parts, such as the updates log or `status:`, keeps it, `lens_verdict.py` § Subject; green with carried warnings counts, § Carried warnings; above the round cap green through a holder's decision, § Round cap); the checkout's copy of the plan is never read, so a stale or missing one selects what main carries | `board.py select <KEY>: refused (plan on main\|refiner\|ready gate\|tier\|lenses)`, then the group's lines; a later group does not run |
| `move <KEY> on_hold --reopen T` | a non-blank reopen trigger, kept in the row as `reopen` | `board.py move <KEY> <state>: refused: <reason>`, one line per failure |
| `move <KEY> backlog --epic EPIC` | exactly one `*-epic.md` under `docs/plans/` names `EPIC` (`ticket:`, `epic:` or `linked_epics:`), and its `status:` starts `approved` | as above |
| `move <KEY> selected` | always refused: `use board.py select` | as above |
| `move <KEY> in_progress [--fast]` | the key's last row in the transitions log is `selected`; with `--fast` from `backlog` or from no row (the fast lane of L0 §Units: no plan file, row `via: fast`); from `in_review` or `in_test` only with `--reopen "<reason>"` (a revert of the merged PR, a failed test), kept as `reopen` | as above |
| `move <KEY> in_test` | the crew maps an In Test status (`board.states.in_test`, default null: no In Test step) and the key is `in_review`; owned per § Several humans | as above; `the crew maps no in_test status` without the mapping |
| `move <KEY> in_review --pr REF…` | every `REF` (a URL, `<owner>/<repo>#<n>`, or a bare number) is `MERGED` by `gh pr view` and carries `<KEY>` as a whole token in its head branch or title, or on a body line that starts with `Ticket(s)`, `Refs`, `Closes`, `Fixes`, `Resolves` or `Delivers` followed by a colon or directly by a key (a story delivered by a bundle PR or another story's PR); a bare number is refused as ambiguous when the plan's phases name a `**Repo:**` other than the checkout's `origin` | as above |
| `move <KEY> done --already-fixed REF [--comment-file FILE]` | from any state but `done`: `REF` (`<owner>/<repo>#<n>` or a URL) is `MERGED` by `gh pr view`, the PR that fixed the story before it was built; the row says `via: already-fixed` and `pr`, the comment names the PR and adds the file's text | as above |
| `move <KEY> done --comment-file FILE` | the key's last row is `in_review` or `in_test` (`last move is <state>, not in_review`; with an owner of `in_test` only `in_test`, § Several humans), and the file holds a line matching `^Not proven:\s*\S`; the row says `via: comment` and the file's text is the comment. A receipts verdict reaches `done` only through `accept.py` (§ Acceptance), which calls `move_done` in process with the entry; the CLI has no `--verdict` | as above |

`select` has no option that waits for, asks
for or records an approval: the gate, the tier and the lenses decide. Every select also needs the
plan on `risk.rules_from` (`plan on main`), and with `humans` the product role and the state's
owner (§ Several humans).

**Tier.** The repo's `risk.command` (called `<command> <base> <KEY>`; it reads the plan from
`HEAD`'s tree and the diff `<base>...HEAD`, prints line 1 `T<0-3>` or `T<n> one-way <class>`) runs
as its blob on `risk.rules_from` in a scratch `git worktree add --no-checkout --detach` tree at that
ref, with base that ref: the caller's branch never reaches the plan's tier. `select` fetches
`origin` first (a failed fetch is one warning). Line 1 outside `^T[0-3]( one-way \S+)?$`, a class
outside `risk.one_way`, a non-zero exit or a plan missing on the ref refuses with `tier not
computed: <reason>`. Without `risk.command` the gate warns `tier check off` and the row says
`tier: none`. `ready_gate.py story` runs the same tier and prints `tier: <line 1>` on stderr.

**Transitions log.** A passing move appends one row to `board-transitions.jsonl` beside the board
(`O_APPEND`, only grows): `{key, from, to, via?, rc?, ts, by, caller?, tier?, carried?, decided?, round?, pr?, reopen?, epic?, ticket}`
(`via` and `rc` on `done` rows only; `carried` on a `selected` row only: the WARNINGs a green
Ready panel carries under `ready_panel.warning_ok_after_rounds`, each `{lens, claim, where}`, also
printed as `carried: <lens>: <claim> (<where>)` lines; the master's worker brief copies them as
must-dos, `skills/master/SKILL.md` § Build (worker brief); `decided` on a `selected` row only: the
lens holders' decisions a Ready panel above `ready_panel.max_rounds` stands on, each `{lens, by,
sentence}`, also printed as `decided: <lens> by <role>: <sentence>` lines; `round` on a `selected` row only, when the
verdict file's round was derived from logged runs (`lens_verdict.py` § Derived round), as
`<N> (derived: …)`, and in a later round `<N> (base: round <M> derived: …)`, also printed as
`round: …`); `from` is
the key's previous row's `to`, `by` the calling session's name (`we-worker close` for its move to
In Review, then with the session as `caller`; `scripts/worker_close.py`, the one closing step after
a merge; a hand move stays possible and the flow report's `Transition writers: In Review` row
counts it as a bypass), `ticket` the transport (`none`,
or `pending` while the session still carries the `carry:` ops and the read-back).

**Ticket.** `board.ticketing` picks the transport (`ticket_adapter.py`). `none`: nothing to carry.
`jira`: the script holds no credential; its last stdout line is `carry: [{"op": "transition", "key":
<KEY>, "status": <board.states.<state>>}]`, which the session executes with its ticketing tool and
verifies by re-reading the status; stderr says so and names the fallback when no ticketing tool
answers (tell the starter which keys stay unmoved, never report the move as done). A `done` move adds a `{"op": "comment", "key": <KEY>, "text":
<the acceptance comment>}` after its transition. The row is written before the line, so an
unexecuted `carry:` shows in `check`.

**Check.** `board.py check --jira FILE` compares a snapshot the session reads with its ticketing
tool (a JSON object key → status name; the caller picks the scope, e.g. Selected, In Progress,
In Review and Done of the running epics; without Done an uncarried `done` move shows no drift) with the log and the board. It reads no ticketing system. Lines,
sorted by key:

- `drift: <KEY> jira "<status>" board <state>`: the status is not the last row's `to`;
- `drift: <KEY> jira "<status>" board none`: no row, and the status is beyond `backlog`;
- `drift: <KEY> session <name> still holds it (board in_review)`: a `sessions[].keys` entry whose
  last row is `in_review`;
- `error: <KEY> jira "<status>" is no board state`: the run goes on over the other keys.

Any line exits 1; none prints `no drift (<n> keys)`. An unreadable or invalid snapshot exits 2.

## Acceptance

`accept.py` (skill `/we:accept`) carries the verdict a repo's receipts job writes for one release
candidate. The job decides; the board re-checks and moves.

**Verdict.** `accept.json`, version 1, in the run's artifact `staging-receipts-<rc>`: `{version, rc,
run_id, run_url, stories: [{key, verdict, oracles: {receipt, ci, walk}, ci_tests, checks: [{id, ac,
persona, status, observed}], walk: [{ac, persona, screen}], not_proven, owner, reason}]}`, `verdict`
one of `done`, `walk`, `red`, `hold`. The contract fixture is `scripts/fixtures/accept/accept_verdict.json`;
a writer pins a byte copy of it.

**Provenance.** `accept.py run --run-id <id>` takes a run id, never a file, and reads before any
download, through one `gh` seam: the run's `path` is `.weside/config.json` `acceptance.receipts_workflow`
(a trailing `@<ref>` ignored) and that file exists on `origin/main`; its `event` is `push` and its
`head_branch` matches `acceptance.rc_tag_glob`; its `head_sha` is the tag's peeled commit
(`git ls-remote --tags origin`) and an ancestor of `origin/main`. Then the artifact must be listed
and not `expired`, and the downloaded verdict must name that `rc` and `run_id`. A failure exits 1
with `refused: run <id> <reason>` (`verdict expired, rerun receipts on the RC` for the artifact) and
writes nothing. Without both config keys it exits 2.

**Per entry.**

| Verdict | What `run` does | Output |
|---|---|---|
| any, last row `done` | nothing | `skip: <KEY> already done` |
| `done` | `move_done` with the entry: last row `in_review`, `verdict: done`, no walk, every check `PASS` and not `NOT TESTABLE`, every receipt AC checked, a non-empty `not_proven`; the row says `via: receipt` and `rc`; the comment is generated (`Accepted by the receipts job <rc> (<run_url>)`, `Oracle:`, `Persona:`, one `Observed:` per check, `Not proven:`) | the row; a refusal prints `board.py move <KEY> done: refused: <reason>` and the run goes on (exit 1) |
| `walk` | one `board-accept.jsonl` line `{rc, key, outcome: walk, acs, persona, screen, ts}`, unless the key already has an open walk from any RC | `walk: <queue line>` or `skip: <KEY> walk already queued (rc <rc>)` |
| `red` | one line `{rc, key, outcome: red, finding, owner, ts}`; `owner` is the entry's when it names a crew member, else `roles.coordinator` | `route: <member> <KEY> <check id> FAIL — <observed>` |
| `hold` | one line `{rc, key, outcome: hold, reason, ts}` | `hold: <KEY> <reason>` |

A (key, rc) already in `board-accept.jsonl` prints `skip: <KEY> <verdict> already recorded for <rc>`:
a rerun writes nothing twice. Every op of the run goes into one `carry:` last line.

**Queue.** `accept.py queue` prints one `<KEY> AC<n> <persona> · <screen> (rc <rc>)` per open walk
(a walk line whose key's last transitions row is not `done`), else `queue: empty`. A walk closes with
`board.py move <KEY> done --comment-file`.

**Sample.** After a `via: receipt` row, every `acceptance.done_sample`-th such row in the log (the
crew's `acceptance` block, default 5) adds one `log` entry `{id: S<n>, kind: sample, title: "Sample
<KEY>: accepted by the receipts job, <keeper> checks it post hoc", ts}` and prints
`sample: <KEY> → <keeper>`; the keeper is `lenses.acceptance.keeper`, else `roles.acceptance`.
`via: comment` rows never count; `done_sample: null` writes none. The count is the log's, so it
survives restarts. `lenses.acceptance.sample` stays the lens sampler's (`lens_verdict.py`,
`samples.jsonl`): neither key moves the other's counter.

## Event lines

A crew whose `.weside/config.json` has an `events:` block runs one event poller per project
(`scripts/command_center/event_poller.py`, started by the SessionStart hook `events_on_start.py`,
by hand with `event_poller.py ensure`):
it reads GitHub and the cluster for the release path and CI (an RC verdict, a stuck rollout, a
blocked release PR or production tag run, main red, a long queue, new issues) and routes each event kind to crew roles
(`event_routes.py` owns the block's schema). Each member's session runs a tail
(`event_tail.py`, whose docstring owns folding, digests and the line text) that writes the lines
routed to its roles into its own inbox; a line never carries a title. A running session starts its
tail without a restart: `hooks/events_on_start.py`, run in the project with `{"session_id": "<its id>"}` on stdin.

What finds no running session waits in the coordinator's delta, `delta.jsonl` in the folder
`event_poller.py path` prints (its row: the `event_poller.py` docstring); a parked session gets only damage kinds. A damage kind (a blocked production
release) without a receiver goes at once to the coordinator's running session and as one `gate`
news item. `event_poller.py status` names the poller, its last round, its sources, the loaded
routes and the running tails.

A route may name `epic_master`: the master session of the event's epic, found over the board's
session lines and the ticket snapshot (`epic_owner.py`, whose docstring owns the resolution). A
master without a companion (`WE_ROLE=master`) runs a tail for it; a worker never does. The `pulls`
source reads one GraphQL query per repo and round and gives one line per transition and head:
`pr_checks_red`, `pr_conflict`, `pr_review_verdict`, `pr_green`, `pr_merged`, each `PR #<n> <repo>
· <what> · <check or head> · <url>`. A pull request's run queued past its limit (`pr_run_queued_long`) goes to the epic's master too, in its hourly digest, unless a route of its own says else; a run without a story key (a fork, a branch without a key) takes the `run_queued_long` route instead, since it has no epic to find. A `main_red` with failing test ids comes from the RC suite's
issue marker (`event_sources.py`) and ends `· owner <session>`; without a running master of its
epic it lands in the delta as `owner delta: coordinator · <epic>`, and a parked master still gets
it (damage to its own epic). `event_poller.py owners --since 24h` lists every red event of the
window with its owner: the receiving session and its delivery time, the delta row, or `owner none`.

An open prompt in any session on the host (a permission prompt, sandbox request or open dialog,
seen in two samples of `claude agents --json` one minute apart) is one `permission_prompt` event
per session and tool call, its line `permission prompt · session <name> · window <window> · tool
<tool> · open since <HH:MM>Z`. A route with `push: true` also posts that line once to the chat
webhook of `events.push` (the poller itself, through the project's secret wrapper); the line then
ends `· push`, or `· no push: <reason>` and the board gets one `gate` item. A prompt in the
receiver's own session, or no running receiver, goes to the `machinery` member's tail, the
coordinator's delta and the board. Nothing answers or approves the prompt; the human does, in that
session's window.

## Staging

A booking reserves the staging environment for one session; an acceptance is a release candidate a
tester is accepting there. Both live as GitHub issues in the crew's repo (the `origin` of the repo
holding the crew file, else the cwd's), so a scheduled RC job on GitHub reads the same state the
board does. `scripts/board_staging.py` owns the issue grammar, pinned by
`scripts/fixtures/staging/issues.json`:

| Issue | Label (crew `release.*`, default) | Title | Body lines |
|---|---|---|---|
| booking | `staging_booking_label`, `staging-booking` | `staging booked by <session>` | `holder: <session>`, `until: <YYYY-MM-DDTHH:MMZ>` |
| acceptance | `staging_acceptance_label`, `staging-acceptance` | `<rc tag>` | `rc: <tag>`, `opened: <UTC>`, `keys: <keys>`; label `staging_past_sla_label` (`past-sla`) after `staging_sla_hours` (12) |

| Verb | Does | Refuses (exit 1) |
|---|---|---|
| `board.py book staging --until <UTC>` | opens one booking issue for the caller's session (its name in `claude agents`), then syncs | `board.py book: refused: <rc> in acceptance since <UTC>` while an acceptance is open; `… booked by <holder> until <UTC> (issue #<n>)` while another booking holds; an `--until` not in the future; an issue list it cannot read |
| `board.py unbook` | closes the caller's own bookings with `unbooked <UTC> by <session>` | `… <session> holds no open booking` |
| `board.py unbook <rc>` | closes that RC's acceptance with `acceptance closed <UTC> by <caller>` (the acceptance run and the tester call it) | `… no open acceptance for <rc>` |
| `board.py staging` | writes the `staging` block and prints `staging: booked by …`, `staging: <rc> in acceptance since … (#<n>)[, past <h> h]` or `staging: free` | an issue list it cannot read (the last block stays) |

A booking whose `until` passed holds nothing; the RC job closes it with `expired <UTC>`. An
acceptance counts as past its SLA by the label or by its `opened` time. The first sync that sees it
past adds one `todo` news item `ST<issue>` for the coordinator (`staging acceptance <rc> past <h> h`);
the block remembers it per issue number, so a hotfix RC that carries the acceptance over (new title
and `rc:`, same issue and `opened:`) adds none. A booking is order, not security: whoever can write
issues can forge or close one.

## The live column

Every minute `hooks/board/probe.py` runs `claude agents --json` and reads, per running session,
only the facts a verdict needs: busy, waiting, blocked, idle or gone; the `WE_ROLE` environment
variable as `master`, `worker` or `other`; the claude-swap profile's folder name from
`CLAUDE_CONFIG_DIR`; and the newest permission mode in the session's transcript. Of a process's
environment it looks at those two keys alone and prints neither value as read. A session that runs
but is not on the board is named in one warning line below the board, `⚠ Live, not on the board:
<names>`, outside the **+ N idle/other** fold, so a session that never wrote its line shows. In a
repo with a crew the column lists only that crew's sessions (`probe.py --crew`: a session whose `cwd`
resolves to the same crew file); one whose `cwd` cannot be read stays, marked unknown. The answer
deliverer matches the board's `updated_by` against this list, so it acts only in its own crew.

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

## Several humans

A crew with `humans` (`scripts/crew.py` § Humans) spans several machines: each human runs
`wclaude --start` with their own sessions, and the machines share only the repo, the ticketing
system and chat. The ticket is the bus between them; chat only wakes a human. Each verb below reads
this session's human (`WE_HUMAN`, else `git config user.email`) and names callers `<role>@<human>`.
With `board.ticketing: jira` no verb reads the ticketing system itself: a first run prints the reads
as `carry:` (`{"op": "search", "state", "jql"}`, `{"op": "read", "key", "fields"}`), the session runs
them with its ticketing tool and hands the results back with `--input FILE`:

```json
{"hits": {"selected": ["PROJ-12", {"key": "PROJ-13", "changed": "2026-11-10T09:12:00.000+0000"}]},
 "tickets": {"PROJ-20": {"status": "In Progress", "labels": ["question-bob"],
                         "comments": [{"author": "bob@example.com", "body": "accept · go", "created": "…"}]}}}
```

Give `changed` with every hit when the tool has it: a hit
without it signals again only a whole `jql_window` after the last signal of its key and state.

**Owners.** In a crew with `humans` every move reads the ticket's status first (the `read` carry
above with `jira`): each machine keeps its own transitions log, so the status is the one state all
share. Only a human who owns the state a story leaves (`owns_states`; several humans may own one
state) moves it on; a refusal out of a running state (In Progress and later, `crew.RUNNING_STATES`)
names the question to its owner, `board.py ask --to <owner>`, instead of the move. A status no
`board.states` entry maps (a Jira "Blocked") has no known owner: with a ticketing system the move is
refused, never decided by the local row; a `tickets` entry without `status` is refused as a form
error. With an owner of `in_test`, Done comes only from In Test. A ticket that already stands at the
target (a session moved it first), or past Selected when `select` comes late, gets its row and no
transition (`ticket already <state>: no transition`), and no owner is asked: the ticket leaves no state; `select` then comments that the ticket stays.
`board.select_unlabel` names labels `select` removes in its carry (an owner's release label).

| Verb | What it does | Refusal |
|---|---|---|
| `select <KEY> [--input FILE]` | as § Moves; in a crew with `humans` the caller must hold `roles.product` on the machine of a human who runs `product` (group `role`) and own the state it leaves (group `owner`), and the plan must be on `risk.rules_from` (group `plan on main`, every crew); after the transition it comments `selected by <role>@<human>, plan <blob>, panel ready-<KEY>` | `board.py select <KEY>: refused (role\|owner\|plan on main\|…)`; an unknown human is refused, never written as `unknown` |
| `move <KEY> <state> [--input FILE]` | as § Moves, after the owner rule above | `board.py move <KEY> <state>: refused: <KEY> is <state>, owned by <human>; …` |
| `signals [--input FILE]` | refused while `board.jql_scope` is unset (a query without it reads every project); for each `board.signals` entry `{state, role, jql_window}` whose role this human runs: the search `[<jql_scope> AND ]status changed to "<status>" after -<jql_window>`; each hit is one `todo` news item `S<n>` with `for` the role and `key`, once per key, state and `changed` (`board-signals.jsonl`); then the replies to this board's open `ask --to` questions (below) | — |
| `claim <KEY> [--release] [--input FILE]` | the comment `claim <role>@<human> <session>` (or `release …`) on the ticket and a line in `board-claims.jsonl`; a claim lives `board.claim_hours` (default 4) from its comment, until the same role, human and session releases it; only a claim on a comment's first line counts, from the account of the human it names or one of `board.shared_accounts` | `board.py claim <KEY>: refused: claimed by <role>@<human> (<session>) at <ts>, live for <n> h`, when another claimant (role, human or session) holds a live claim on the ticket or in the local claims |
| `inbox [--input FILE]` | the search `[<jql_scope> AND ]labels = "<question label>-<me>"`: every ticket that holds an open question to this session's human | — |
| `reply <KEY> <accept\|deny\|followup\|update> [--text T]` | the answer of this session's human on the ticket: the comment `<role>@<human> <kind> · <T>`, then this human's question label off (`{"op": "unlabel", "key", "remove"}`); another human's question stays theirs | an unknown human |
| `withdraw <Q> [--for <Q2>] [--reason T]`, `supersede <Q> --by <Q2> [--reason T]` | the asker (its session name, matched in any case; a nameless `unknown` never matches) or the coordinator takes its own open question off the board: a `withdrawn` or `superseded` line (with `by`, or `for` when it gave way to `<Q2>`) in `board-questions.jsonl`; a question asked with `--to` also gets the comment `<Q> withdrawn` (or `superseded by <Q2>`) and loses its label | another session's question, an id the board and its logs never had (an id already off the queue is no refusal: `<Q>: nothing to withdraw, it is off the queue (<status>, …)`, exit 0; the status is `question_status`, the one definition of open that `show` and the pane share), `--by` naming no other open question; a refused `supersede` of `<Q>` also names each session that withdrew its own question for `<Q>` (`--for`, or `<Q>` in its reason): the caller tells them, since their option is on no board |
| `ask … [--input FILE]` | a `merge-go` in a crew with `humans` reads the ticket's status first | `board.py ask: refused: <KEY> is <status> on the ticket` when it is On Hold; refused too for a status no `board.states` entry maps |
| `ask … --to <human>` | as § Questions and decisions (the cold reader included), for a human on another machine: the item keeps `to` and `label`, the carry is the comment `<question_label> <labels.to> <Name> · <ask> · <labels.recommendation>: <recommendation>` and the label `<question_label lowercased>-<human>`; `--to` naming this session's own human is a plain `ask` | `--to` naming no human of the crew, or a `--key` that is a plan slug |

**Replies.** `signals` reads the ticket of each open question this board sent with `--to`: a comment
created after the question whose `author` is one of that human's accounts (`humans.<slug>.email` or
`account_id`, never the display name: anyone can name themselves Bob), or whose first word is
`<role>@<human>` from that human's account or one of `board.shared_accounts` (accounts several humans
write from), is a reply; another human with the same role never answers for them, and the question
comment itself is never one. Its first word, in any case,
when it is one of `accept`, `deny`, `followup`, `update`, is the answer kind, else `followup`; the reply's text is the `quote`. It lands as an answer
line with `via: ticket`, and the deliverer carries it to the asker like a press (§ Delivery); each
reply once. The label taken off without a reply is the answer `update` (is the question still
current?). `board.py reply` writes the answer and takes the label off in one carry. An Accept, Deny
or Withdraw closes the question: `signals` reads its ticket no more, and a later comment there
answers nothing. A claim comment counts only from the account of the human it names or a shared
account, the local claims always.

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
