---
name: resume
description: >
  Resumes this session's work after a usage-limit stop: open items, workers, monitors.
  Triggers: "/we:resume", "weiter".
---

# /we:resume

Continues the work this session was doing when a stop cut it off. The built-in `/resume` reopens an
earlier conversation; `/we:resume` runs inside the conversation and restarts its work. One word from
the user is the whole instruction: ask nothing the open-items list already decides.

Invocation: `/we:resume` (this session) · `--broadcast` (every running session of the crew, § Broadcast).

1. **Open items.** Read the open-items list ("Offen", "what's left", "next") of the last report in
   this session. After a compaction, read the transcript tail for it. No list → name the last task
   in one line and continue it.
2. **Workers.** `ListAgents`, then per worker (before a quota pause a Lead secured each worker's
   tree with a checkpoint (**Checkpoint** in `references/worker-dispatch.md`): the parked work is on
   `wip/<branch without its type prefix>` and in the worktree's last commit):
   - stopped mid-task → `SendMessage(to=<name>, "continue where you stopped")`;
   - already reported → shut it down and verify it is gone (`TaskStop`, or no process under
     `/proc`).
3. **Waits.** Re-arm the monitors and background waits the stop killed: the CI watch on each open PR
   (`${CLAUDE_PLUGIN_ROOT}/scripts/watch-pr-checks.sh <PR>` as a background command, `--until-merged` for an armed PR; an
   event-routed master re-arms none and reads each PR's state once with `gh pr view <PR>`, the lines carry the rest:
   `references/session-traps.md` § CI and checks), rollout and deploy waits.
4. **Go.** Say in one line what resumes, then work the open items in their order. A merge outside a
   run's standing auto-merge (`master` § Close the run) or a release still needs the user's word.

## Broadcast

After a stop that hit the whole crew, one call resumes every session. Recipients, the caller's own
part and tracking: `${CLAUDE_PLUGIN_ROOT}/references/broadcast.md`.

1. **Brief.** Each recipient gets: "Run `/we:resume` on your own session. Reply to <caller's name>
   with one line `RESUME · <your name> · <what resumes>` or `RESUME · <your name> · nothing open`."
2. **Own resume.** Run steps 1–4 above on your own session; your `RESUME · …` line is a row like
   the others.
3. **Close.** One line per row.
