---
name: standup
description: >
  Picks you back up: what we work on, where it stands, what you must do next; read-only.
  Triggers: "/we:standup", "/we:standup all", "where am I", "status" as the whole message.
needs: [ticketing]
---

# /we:standup

Read-only: run one script, render it, judge the utilization; write nothing, dispatch nobody, move
no ticket. The reader needs, in under 30 s: is it running, what was achieved, what comes, where does
it stick, and what must the human decide. When the user's instruction files define a status form (a
sentence cap, a language), that form wins over the layout below.

## 1 · Scope (first hit wins)

1. A key in the arguments (`/we:standup PROJ-123`): an epic key gives the epic detail, a story key
   the story with its epic's intent. `--branch` → § 4.
2. The ticket key of the current branch (`<type>/<KEY>-…`).
3. Story keys this conversation dispatched or opened PRs for (only from its own context; a fresh
   session or a subagent skips this step).
4. Nothing found → the portfolio: every active epic of the repo.

A build master or worker that types `status` or "where am I" therefore keeps seeing its own story
(steps 2–3); only a session without a key of its own gets the portfolio. `/we:standup all` skips the
steps and shows the portfolio anyway, so the human gets the overview of every epic from any session.
`/we:standup --broadcast` asks every running session for its own state instead (§ 5).

## 2 · Gather and render (one call)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/standup.py [KEY | all] [--conversation-keys K1,K2] --md --lang <de|en>
```

`KEY` from step 1, or `all` passed on unchanged: the script skips the branch and conversation keys
only when it sees it. The keys of step 3 as `--conversation-keys`, the language from the user's
instruction files (default `en`). The script owns the scope order, every source and every number
(its docstring: sources, light rules, trend band, signal rules); print its output as it comes.
A first line `view: branch` → render § 4 instead. A source it could not read stands under its gaps
as `<source>: not read (<why>)` and as `n/a` in the tables: never fill it by inference. `--json`
prints the same document for a reader that needs fields (`orchestration`: master → epic → stories →
workers).

The epic and story views walk up to the epic's `serves:` metric of the goal file and show it in the
intent (serves <metric>), so every slice names the number it moves.

The section of decisions bundles the board's open questions to the human and the `## Open Fork` of
each story plan in scope, ranked by what it holds up, with its recommendation, so the human answers
them in one pass instead of question by question. Add this conversation's unanswered questions to
the user, and the due items of the repo's due-items file when its instruction files name one: only
you know them, the script does not.

## 3 · Utilization and acceleration

Below the script's output, add one section in the user's language (de: „Auslastung und
Beschleunigung"), drawn only from its utilization table and signals:

1. One verdict sentence: does the work move fast — yes or no, with the numbers behind it (busy and
   free worker slots, idle masters, waiting hours, CI rounds).
2. When signals fired: the biggest bottleneck (the signal holding the most keys or hours), then one
   to three proposals. Each names its effect, its evidence (the signal's numbers, source and
   threshold) and who carries it out (the signal's actor).
3. No signal fired → the verdict sentence alone.

| Good proposal | Bad proposal |
|---|---|
| "Start a master for PROJ-9004: selected without master (`selected_without_master`, threshold ≥ 1) — coordinator" | "More parallel work would help" — no signal, no number |

Every proposal stands on a fired signal: an idea without a measurement does not appear. Propose,
never start: the command stays read-only.

- [ ] the script ran once and its output stands unchanged above the section
- [ ] the verdict sentence carries numbers from the utilization table
- [ ] each proposal cites one fired signal id, its evidence, source, threshold and actor

## 4 · Branch view (`--branch`, a key without an epic)

`/we:master`'s user-merge close embeds this view.

```text
STANDUP — <KEY> · <branch> · PR #<n> <state> · CI <green|n red|pending> · tree <clean|n dirty>
ACHIEVED  <≤ 3 lines: what is now true — a merged PR, a green gate, a closed phase>
NEXT      <story key(s) and the command that starts them — or: nothing queued>
YOUR MOVE <one action with its command — or: nothing, because …>
```

Gather for the argument key when one is given (its plan, ticket and PR found by key), else for the
current branch: `git status -sb`, the plan and ticket, the PR and its required checks,
`git log --oneline origin/<default>..HEAD` (at most 10, current branch only). The session title should carry the ticket
key; if it does not, print `/rename <KEY>` once, unless the session is a bound companion session
(`${CLAUDE_PLUGIN_ROOT}/references/companion-session.md` § Name and binding).

## 5 · Broadcast (`--broadcast`)

The full picture for a coordinator: every running session reports its own state, the caller sums
up. Still read-only: the briefs and replies are messages, nobody writes or starts anything.
Recipients, the caller's own part and tracking: `${CLAUDE_PLUGIN_ROOT}/references/broadcast.md`.

1. **Brief.** Each recipient gets: "Reply to <caller's name> within 10 minutes with one line
   `STAND · <your name> · <KEY or epic> · running: <what> · waiting on: <whom or what> · next:
   <step>`. Read only your own state; finish no step for it."
2. **Own line.** Write your own `STAND · …` line from this conversation and § 1's scope.
3. **Summary.** Once every row replied, or 10 minutes after the briefs (a background `sleep 600`
   wakes you), print one table (session, key, running, waiting on, next), then three lines: what waits on the human, which session waits on which, and the
   biggest blocker.

- [ ] every recipient and the caller hold a row, silent ones as `no answer`
- [ ] the summary names what waits on the human, or says nothing does
