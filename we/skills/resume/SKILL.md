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

1. **Open items.** Read the open-items list ("Offen", "what's left", "next") of the last report in
   this session. After a compaction, read the transcript tail for it. No list → name the last task
   in one line and continue it.
2. **Workers.** `ListAgents`, then per worker:
   - stopped mid-task → `SendMessage(to=<name>, "continue where you stopped")`;
   - already reported → shut it down and verify it is gone (`TaskStop`, or no process under
     `/proc`); never restart it.
3. **Waits.** Re-arm the monitors and background waits the stop killed: the CI watch on each open PR
   (`${CLAUDE_PLUGIN_ROOT}/scripts/watch-pr-checks.sh <PR>` as a background command), rollout and
   deploy waits.
4. **Go.** Say in one line what resumes, then work the open items in their order. A merge or a release
   still needs the user's word.
