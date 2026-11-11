# Several humans (`/we:setup` § 4a.3)

What setup asks and writes for the humans of a crew. The keys, their types and defaults belong to
`${CLAUDE_PLUGIN_ROOT}/scripts/crew.py` (docstring § Humans and `board`); what the verbs do with them
to `${CLAUDE_PLUGIN_ROOT}/docs/board.md` § Several humans. Every value goes into `.weside/crew.json`
only when it differs from `crew.py`'s `DEFAULTS`.

## Contents

- One human or several
- The humans: one block to correct
- What comes with several humans
- Write and validate
- Start, per human
- Example

## 1. One human or several (ask once)

"Do several people work in this repo, each on their own machine with their own sessions?" Why: then
the machines share only the repo, the ticketing system and chat, and the crew file must say who runs
what where.

- **No** → `human`: the name and `decides` (the decisions only that human takes) as one line to
  correct. Nothing else in this file applies; a one-human crew stays as it is.
- **Yes** → steps 2 to 5. Keep `human` beside `humans`, set to the deciding human's name and
  `decides`: the merge hook's refusals and the compact notice still name `human.name`. A re-run on a
  crew with `humans` starts at step 2 with the file's values as the proposal.

## 2. The humans: one block to correct

Propose every human as one JSON block (the shape of § Example), never as one question per field:

| Key | Proposal |
|---|---|
| slug, `name` | the slug lower case (`[a-z0-9][a-z0-9_-]*`), usually the first name |
| `email` | for the human at this machine `git config user.email`; ask for the others. `wclaude --start` finds the human by it, and a ticket comment counts as theirs only from it or `account_id` |
| `account_id` | optional: the ticketing account id (a Jira accountId), when the ticketing tool returns comment authors as ids; look it up with the ticketing tool rather than ask for it |
| `decides` | the decisions that human owns, in the crew's words (`money`, `prod`, `product direction`); the first human with `decides` is the crew's deciding human |
| `owns_states` | the product role's human `on_hold`, `backlog`; the coordinator's human `selected` to `done`. Only an owner moves a story on from its state; a state nobody owns, anyone moves, so name every state in the proposal |
| `runs` | the role keys bound in step 4a.2 that start on that human's machine, the specialists woken there, and `masters` where epics are built; each bound role on one machine |
| `companions` | role key or member slug → that human's own name for it, only where it differs from the member's `name` |

A ticketing account several humans write from goes to `board.shared_accounts` only when the user
names one; never propose it.

## 3. What comes with several humans

Each item is skippable; a skip keeps `crew.py`'s default.

- `board.ticketing`: `jira` when step 2 of setup confirmed Jira: the ticket carries every move,
  claim and question between machines (default `none`: say that signals, claims and questions
  across machines then stay off).
- `board.jql_scope`: propose `project = <KEY>` from setup's question 2. Required with any signal:
  `board.py signals` refuses while it is unset, so a skipped scope means no `board.signals` either.
- `board.signals`: one `{state, role, jql_window}` per hand-over between machines. Propose
  `{"state": "selected", "role": "coordinator", "jql_window": "35m"}` (the coordinator's start
  signal), plus one for each state whose next owner sits on another machine than the mover, with
  the role that picks it up there. The window is a little longer than the coordinator's sweep.
- `board.claim_hours`: how long a ticket claim lives (default 4).
- `labels.to`: the word before a human's name in a ticket question, in the crew's language (`an`
  for German); `question_label`: the question's opening word (default `QUESTION`), its ticket label
  `<question_label lowercased>-<slug>`.
- `board.states.in_test`: only when the ticketing system has an In Test status. Read the project's
  statuses with the ticketing tool rather than guess; found → propose the mapping and which human
  owns `in_test` (Done then comes only from In Test); none → write nothing; unreadable → ask once.

## 4. Write and validate

Write the block with the rest of step 4a.3 and run
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/crew.py validate --strict`. Relay every refusal word for word,
correct it with the user and run again until it prints `ok`. A re-run shows the diff of `human`,
`humans`, `board` and `labels` against the file and asks before replacing.

## 5. Start, per human

Tell each human how their machine starts:

- `git config user.email` there equals their `email`, or `export WE_HUMAN=<slug>` (the slug wins).
- `wclaude --start` (installed in setup § 5) starts the coordinator when that human runs it, else
  their first role in `runs`, opens the product role in its own tmux window when they run it, and
  `/we:start` offers the rest of their `runs`. `wclaude --start --role <key>` starts one more.

## Example

A complete crew file for two humans; `scripts/validate-consistency.py` (check `setup-humans`) loads it
with `crew.py validate --strict` and requires it to show every `humans` field `crew.py` knows.

```json
{
  "version": 2,
  "skill_prefix": "acme",
  "human": {"name": "Alice", "decides": ["money", "prod"]},
  "question_label": "FRAGE",
  "labels": {"to": "an", "recommendation": "Empfehlung"},
  "roles": {"product": "paula", "coordinator": "otto", "architecture": "otto",
            "acceptance": "tess"},
  "members": {
    "paula": {"name": "Paula", "title": "Product Owner", "components": ["Shop"]},
    "otto": {"name": "Otto", "title": "Coordinator"},
    "tess": {"name": "Tess", "title": "Tester"}
  },
  "humans": {
    "alice": {"name": "Alice", "email": "alice@example.com", "account_id": "acct-alice",
              "decides": ["money", "prod"],
              "owns_states": ["selected", "in_progress", "in_review", "in_test", "done"],
              "runs": ["coordinator", "architecture", "acceptance", "masters"]},
    "bob": {"name": "Bob", "email": "bob@example.com", "decides": ["product direction"],
            "owns_states": ["on_hold", "backlog"], "runs": ["product"],
            "companions": {"product": "Penny"}}
  },
  "board": {
    "ticketing": "jira",
    "jql_scope": "project = SHOP",
    "states": {"in_test": "In Test"},
    "signals": [{"state": "selected", "role": "coordinator", "jql_window": "35m"}],
    "claim_hours": 6
  }
}
```
