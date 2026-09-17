---
name: standup
description: >
  Where this branch stands: ticket, PR, CI, a recap of its commits, what is left, and whether
  you must act. Triggers: "/we:standup", "wo stehen wir", "where am I", "what's the state".
---

# /we:standup — Where this branch stands

Read-only: reads git, the plan, the ticketing mirror and `gh`; writes nothing, dispatches
nobody, transitions no ticket. One screen, then out.

**Who reads this.** A person with ten Claude windows open, coming back to this one after an hour
in the others, who has to re-learn what *this* window was doing. So the screen answers three
questions in order, concretely and with names: **what was achieved** (not what ran — what is
now true that was not), **which story or stories come next** (keys, not "the roster"), and
**what the human must do** (a merge, a decision, a device round — or nothing, said as nothing).
`/we:orchestrate` and `/we:ci-review` end by running this skill, so it is the last thing a
window says before it goes quiet.

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
7. **Name** — the tmux window title should read the ticket key or the epic's one word
   (`${CLAUDE_PLUGIN_ROOT}/references/session-name.md`); if it does not, set it now and print the
   `/rename` line once. A window whose title still says the last job is the reason the human
   has to ask.

## Output

```text
STANDUP — {KEY} · {branch}
  story     {title} · {ticket-state} · phases {done}/{total}
  pr        #{n} {state} · checks {n green / n red / pending} · review {decision}
  tree      {clean | n dirty} · {ahead/behind}
  in flight {worker names, or —}

  ACHIEVED  {≤3 lines: what is now true that was not — a number, a merged PR, a closed ticket}
  NEXT      {story key(s) and the command that starts them — or: epic closed, nothing queued}
  OPEN      {at most three items someone owes, each with an owner — or: nothing}

  YOUR MOVE
  → {the one action, with the command}          # or: nothing — {why}
```

`OPEN` is work, not knowledge: a thing worth knowing goes in the plan or the state file, never
here. More than three items under `OPEN` means the story is not finished — say that instead.

## Rules

- **The verdict is one item, never a menu.** Two candidates → name the one that unblocks the
  other, and put the second behind it.
- **"Nothing to do" is a complete answer** — print it plainly instead of inventing a chore.
- Report a missing source (no `gh`, no plan, no ticketing) as a named gap; never fill the hole
  with an inference.
- Never write, never dispatch, never transition. A status that changes state is not a status.
