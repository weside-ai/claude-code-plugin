---
name: standup
description: >
  Where this branch stands: ticket, PR, CI, a recap of its commits, what is left, and whether
  you must act. Triggers: "/we:standup", "wo stehen wir", "where am I", "what's the state".
---

# /we:standup — Where this branch stands

Read-only: reads git, the plan, the ticketing mirror and `gh`; writes nothing, dispatches
nobody, transitions no ticket. One screen, then out.

**Neighbours, same landscape, different cut.** `/we:map` is wide and shallow across every plan ·
`/we:saga` / `/we:epic` go deep on one artifact · `/we:handoff` writes a durable file for the
*next* session · `/we:standup` is **this branch, right now**. `/we:orchestrate`'s `status`
is a different thing: the Lead's spoken roll-up mid-wave, not this dashboard.

## Steps

1. **Tree** — `git status -sb`: branch, ahead/behind, dirty files.
2. **Story** — key from the branch (`feat/{KEY}-…`) → `docs/plans/{KEY}-story.md` frontmatter and
   its `### Phase` blocks (done vs open) + the ticket state
   (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`). No key or no plan → say so in one line and
   carry on; a branch without a story is a fact, not an error.
3. **PR + CI** — `gh pr view --json number,state,statusCheckRollup,reviewDecision` and
   `gh pr checks`. No `gh` → name the gap.
4. **Recap** — `git log --oneline <base>..HEAD` (cap 10) plus the uncommitted diff, boiled to
   ≤ 3 lines of *what changed and why*, never a commit dump.
5. **In flight** — `ListAgents` for this session's teammates, plus `docs/plans/*-state.md` if the
   branch has one. A running worker is the difference between "nothing to do" and "wait".
6. **Verdict** — one move, and it may be *nothing*.

## Output

```text
STANDUP — {KEY} · {branch}
  story     {title} · {ticket-state} · phases {done}/{total}
  pr        #{n} {state} · checks {n green / n red / pending} · review {decision}
  tree      {clean | n dirty} · {ahead/behind}
  recap     {≤3 lines}
  in flight {worker names, or —}
  open      {one line per remaining item}

  YOUR MOVE
  → {the one action, with the command}          # or: nothing — {why}
```

## Rules

- **The verdict is one item, never a menu.** Two candidates → name the one that unblocks the
  other, and put the second behind it.
- **"Nothing to do" is a complete answer** — print it plainly instead of inventing a chore.
- Report a missing source (no `gh`, no plan, no ticketing) as a named gap; never fill the hole
  with an inference.
- Never write, never dispatch, never transition. A status that changes state is not a status.
