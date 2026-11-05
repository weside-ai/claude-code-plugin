---
name: lens
description: >
  Lens panel: fresh lens agents judge a plan (ready) or a PR diff (t2) in parallel; verdicts
  recorded and checked. Trigger: "/we:lens".
---

# /we:lens — the lens panel

You run the panel; the lens agents judge. Start it with `lens_verdict.py plan`, spawn every entry in one message, record each answer with `write`, end with `check`.
You never judge in a lens's place, never edit a verdict file and never pass a lens your own context: a lens is a fresh agent.
The verdict and the green rule are computed by `lens_verdict.py` (its module docstring owns them); a red panel turns green only through a fresh panel on a new plan blob or head.
Wanted stop: the `check` lines. Every other status note goes with the next tool call.

```text
/we:lens ready <KEY>              the Ready panel on docs/plans/<KEY>-story.md (before the story moves to Selected)
/we:lens t2 <PR>                  the T2 panel on the PR's head
/we:lens samples [--keeper SLUG]  the sampled green verdicts a keeper has not read
```

`LV` below is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lens_verdict.py"`, run from the repo the plan or PR belongs to.
Scratch files go to the session's scratchpad directory (`$S`).

## 1. Start the panel

Run `LV plan ready <KEY>` or `LV plan t2 <PR>`. It writes a fresh verdict file bound to today's plan blob or
PR head and prints the dispatch entries as JSON (`id`, `lens`, `agent`, `questions`, `registry`, and `plan`
plus `plan_blob`, or `pr` plus `head`). Exit 1 (no plan file, head unknown) or 2 (crew file, verdict
directory): relay the line and stop.

An entry whose `agent` is not one this plugin ships (`we:lens-product`, `we:lens-architecture`,
`we:lens-acceptance`) is not dispatched: record it with `LV write <id> <lens> --failed "no agent <agent>"`.

## 2. Dispatch every entry in one message

One `Agent` call per entry, all in one message: `subagent_type` = the entry's `agent`, `prompt` = the
entry's JSON and nothing else, no `model`, no fork, no `isolation`. The agents run in parallel; wait for all.

## 3. Record each answer

Per lens, with the Write tool, save the agent's final message verbatim to `$S/lens-<id>-<lens>.txt` (never
through a shell heredoc or `echo`: the answer is foreign text), then:

```bash
LV write <id> <lens> < "$S/lens-<id>-<lens>.txt"
```

- Exit 0 prints `lens <lens>: green|red`.
- `no parseable answer`: spawn that agent once more with the same entry; a second miss leaves the lens
  missing (red). Say so.
- `key '<k>' refused` or another refusal of the answer's shape: spawn that agent once more with the entry
  plus the refusal line; a second refusal: `LV write <id> <lens> --failed "<the refusal line>"`.
- On T2, run the red arms (§ 4) before this step.

## 4. T2 only: run the red arms

Every BLOCKING or WARNING finding in an answer carries `red_arm.command`. Per finding:

1. Save the command alone to `$S/arm.txt` (Write tool), then `LV arm < "$S/arm.txt"`. `arm: not run: …`
   means the command is not in test form: never run it, show it to the user, leave its `exit` unset
   (`write` keeps the finding standing with `run: false`).
2. `arm: run`: run it once per PR head in a detached worktree of its own, never in the main worktree or yours:

   ```bash
   git worktree add --detach "$S/lens-arm-<PR>" <head>
   cd "$S/lens-arm-<PR>" && timeout 600 <command>; echo "exit=$?"
   ```

   The command names its tests one by one, never a whole suite. A command that starts tests takes the
   repo's test slot or heavy-gate lock as the repo's instruction files name it; waiting at the lock is
   no result. Run the worktree bootstrap the repo names first when the command needs it.
3. Put the exit code into that finding's `red_arm` as `"exit": <n>` in `$S/lens-<id>-<lens>.txt` (Edit
   tool, nothing else changed), then `LV write` as in § 3. Exit 0 refutes the finding; 124 (timeout), 126,
   127 or above 128 (a signal) prove nothing and `write` refuses the finding as without red arm.
4. After the last arm: `git worktree remove "$S/lens-arm-<PR>"` in a command of its own.

`write` refuses a BLOCKING or WARNING finding without `red_arm`: spawn that lens once more with the
refusal line; a second refusal: `LV write <id> <lens> --failed "finding without red arm"`.

## 5. Check and report

Run `LV check <id>` and relay its lines: one per lens (`green`, `red (<why>)`, `missing`), a `stale` line
when the plan or head moved, and `panel <id>: green|red`. Exit 0 only for green. The board's move to
Selected reads the Ready panel itself (`board.py select`); the merge of a two-way T2 PR reads the T2 panel.
The verdict file lives under `<git common dir>/we-lens/`, outside the tree: never commit it, never edit
it by hand.

## Samples

`LV samples --keeper <slug>` lists `<id>\t<lens>` per green verdict that was sampled (every
`lenses.<lens>.sample`-th green one) and not yet read. The keeper reads the verdict file and the subject,
judges whether the lens was right, and runs `LV sampled <id> <lens>`. A lens that was wrong gets a sharper
line in its question file, from the keeper; nobody waits on a sample.
