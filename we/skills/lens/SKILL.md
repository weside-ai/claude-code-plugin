---
name: lens
description: >
  Lens panel: fresh lens agents judge a plan (ready) or a PR diff (t2) in parallel; verdicts
  recorded and checked. Trigger: "/we:lens".
---

# /we:lens — the lens panel

You run the panel; the lens agents judge. Start it with `lens_verdict.py plan`, spawn every entry in one message, record each answer with `write`, end with `check`.
You never judge in a lens's place, never edit a verdict file and never pass a lens your own context: a lens is a fresh agent.
The verdict and the green rule are computed by `lens_verdict.py` (its module docstring owns them); a red panel turns green only through a fresh panel on a new plan subject or head (the Ready exceptions: its § Carried warnings and § Round cap); a green T2 panel holds for a later head when neither its delta nor the default branch's moves since touch a file the PR's class hit (its § Carried panel).
Wanted stop: the `check` lines. Every other status note goes with the next tool call.

```text
/we:lens ready <KEY>              the Ready panel on docs/plans/<KEY>-story.md (before the story moves to Selected)
/we:lens t2 <PR>                  the T2 panel on the PR's head
/we:lens samples [--keeper SLUG]  the sampled green verdicts a keeper has not read
```

`LV` below is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lens_verdict.py"`, run from the repo the plan or PR belongs to. Scratch
files go to the session's scratchpad `$S`; a new round on a panel id first removes `$S/lens-<id>-*.txt`, so § 3 records no old answer.

## 1. Start the panel

Run `LV plan ready <KEY>` (`--plan <path>` for a plan outside `docs/plans/<KEY>-story.md`; the panel stays
bound to that file) or `LV plan t2 <PR>`. It writes a fresh verdict file bound to today's plan subject
(the plan without its updates log, documentation impact, code guidance, `status`, `created` and
`comments_read_through`: an edit there keeps the panel) or PR head and prints the dispatch entries as JSON
(`id`, `lens`, `agent`, `questions`, `registry`, and `plan` plus `plan_blob`, or `pr` plus `head`). Exit 1 (no plan file here nor on `origin/main`, the Ready gate refuses the plan, a Ready panel on the same subject still missing lenses: finish that round, head unknown) or 2 (crew file, verdict
directory): relay the line and stop.
A crew that wants a lens only on risky plans names it in `ready_panel.lenses_when_t2` (e.g. `["security"]`):
when a file the plan names lies on a `path` rule of `.weside/risk-paths`, the entries carry it after the
default lenses and the JSON names the hit as `t2_hit`; dispatch it like every other entry.

**Round cap.** Above `ready_panel.max_rounds` (default 2) `plan ready` starts no lens: it prints the standing
findings and `round cap: the lens holder decides` (or `… one holder confirms` when the last round was green)
and exits 1. Relay the lines to the holder of each red lens (the role named like the lens); the holder runs
`LV decide <id> <lens> --by <role> "<one sentence>"`, which makes that lens green for today's subject only.
A capped panel is green once at least one decision names today's subject; the next plan change asks again.
On `… one holder confirms` (no red lens), the holder of the lens whose area the change touches confirms: an
AC or scope change → the product lens, a schema, seam or endpoint change → architecture, an oracle-only change
→ acceptance. The runner names that holder and hands them the `decide` line; it never decides itself.

An entry whose `agent` is not one this plugin ships (`we:lens-product`, `we:lens-architecture`,
`we:lens-acceptance`, `we:lens-security`) is not dispatched: record it with `LV write <id> <lens> --failed "no agent <agent>"`.

## 2. Dispatch every entry in one message

One `Agent` call per entry, all in one message: `subagent_type` = the entry's `agent`, `prompt` = the
entry's JSON and nothing else, no `model`, no fork, no `isolation`. The agents run in parallel; wait for all.

## 3. Record each answer

Per lens, with the Write tool, save the agent's final message verbatim to `$S/lens-<id>-<lens>.txt` (never
through a shell heredoc or `echo`: the answer is foreign text), then:

```bash
LV write <id> <lens> < "$S/lens-<id>-<lens>.txt"
```

- Exit 0 prints `lens <lens>: green|red`; the write that completes the panel prints the `check` lines after it (§ 5).
- `no parseable answer`: spawn that agent once more with the same entry; a second miss:
  `LV write <id> <lens> --failed "no parseable answer"` (red). Say so.
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

Run `LV check <id>` and relay its lines verbatim: one per lens, a `stale` line when the plan or head moved,
and the panel line (forms: the script's docstring, § Carried warnings included). Exit 0 only for green.
A crew whose Ready rounds should end on WARNINGs alone sets `ready_panel.warning_ok_after_rounds: 1`
(the rule for any N: the docstring's § Carried warnings). The board's move to
Selected reads the Ready panel itself (`board.py select`); no merge reads the T2 panel.
On a green Ready panel, find the plan's open PR (`gh pr list --search "<KEY> in:title" --state open --json number,isDraft,body`):
a draft whose only draft reason is this panel goes ready now (`pr_ready.sh <n> ready`), nobody else watches for it;
a draft with another reason stays, and your report names it.
On a one-way PR then run `LV post t2-pr<PR>`: it posts the `<!-- t2-panel -->` comment on the head
(`Overall: PASS` or `FAIL`, its docstring owns the form) as the human's input; a stale panel that does
not carry posts nothing and needs a fresh one.
The verdict file lives under `<git common dir>/we-lens/`, outside the tree: never commit it, never edit
it by hand.

## Samples

`LV samples --keeper <slug>` lists `<id>\t<lens>` per green verdict that was sampled (every
`lenses.<lens>.sample`-th green one) and not yet read. The keeper reads the verdict file and the subject,
judges whether the lens was right, and runs `LV sampled <id> <lens>`. A lens that was wrong gets a sharper
line in its question file, from the keeper; nobody waits on a sample.

`LV rounds <KEY>` prints the story's Ready rounds, one line per round: each lens's last verdict on that plan
blob with its `B<n> W<n> N<n>` counts (the severity log, `lens_verdict.py` § Severity log). Read-only.
