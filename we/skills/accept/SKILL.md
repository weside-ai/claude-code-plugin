---
name: accept
description: >
  Carries a receipts job's verdict onto the board: green stories to Done with their generated comment,
  walks queued, red findings routed. Triggers: "/we:accept [run-id]", "accept the RC".
---

# /we:accept

The receipts job of a release candidate decides; this skill carries. It reads one run's verdict
(`accept.json` in its artifact), moves each green story to Done, queues the walks and routes the red
findings. You judge nothing here: a verdict you disagree with is a finding for the job's owner, not
a hand move. Format, files and entry rule: `${CLAUDE_PLUGIN_ROOT}/docs/board.md` § Acceptance.

## 1 · Run (the acceptance role, after each RC's receipts job)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/accept.py run --run-id <run-id>
```

- Pass the run id of the RC's receipts run, never a file: the script checks the run's provenance
  (the repo's `acceptance.receipts_workflow`, a `push` of a tag matching `acceptance.rc_tag_glob`,
  the tag's commit on `origin/main`, the verdict naming that RC and run) and downloads the artifact
  itself.
- `refused: run <id> …` or `verdict expired, rerun receipts on the RC`: report the line to the
  machinery owner and stop. Never work around it: no downloaded file, no hand-made verdict.
- Exit 1 with `board.py move <KEY> done: refused: …` lines: those entries stayed In Review; the
  others ran. Report each refused key with its line.

## 2 · Carry what it printed

- `carry: [...]` (last line, ticketing `jira`): execute every op in order with the ticketing MCP
  (each `transition`, then its `comment`), then re-read each ticket's status. A failed op: report
  it; `board.py check` shows the gap later.
- `route: <member> <KEY> <check> FAIL — <reason>`: send the line to that member (`SendMessage` to
  their session) as a finding on the story; it stays In Review.
- `hold: <KEY> <reason>`: the job could not judge the story; send it to the story's master.
- `sample: <KEY> → <keeper>`: the board holds a `sample` item; the keeper checks that story post hoc.

## 3 · Walk the queue

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/accept.py queue
```

One line per open walk: `<KEY> AC<n> <persona> · <screen> (rc <rc>)`. Start one acceptance worker
per line through the crew's `launch.worker` with the agent `we:lens-acceptance`, the persona and the
screen. Its comment names what it observed and carries a `Not proven: <what>` line; then:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board.py move <KEY> done --comment-file <comment.md>
```

A story with no built commit in any RC range (another repo, docs only) closes the same way, with
its own evidence in the comment.

## Done when

- [ ] every `done` entry has its row in `board-transitions.jsonl` and its `carry:` ops executed
- [ ] every `route:` and `hold:` line reached its member
- [ ] every open walk has a worker, or is named in your report with why it waits
