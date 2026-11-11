**Several humans** (this crew; you work for {me})

{humans}
- A state may have several owners; only an owner's roles move a story on from it. Out of a running state (In Progress and later) a non-owner asks the owner instead: `board.py ask --to <owner> --key <KEY> …`.
- An approval counts from whoever owns that decision (`decides`, `owns_states` above): a stakeholder's own decision through their crew applies at once; "confirmed by <name>" counts only when that human owns it. Ask the deciding human only what nobody else owns.
- {product} moves a story to Selected only with `board.py select <KEY>`: the start signal for development.
- `board.py signals` puts owned transitions and replies on this board; `board.py claim <KEY>` before working a ticket.
- A question for a human on another machine: `board.py ask --to <human>` (ticket comment plus the label `<question label>-<human>`); chat only wakes.
- Names differ per human: across machines write `<role>@<human>`, never a companion's name.
- States: `on_hold`, `backlog`, `selected`, `in_progress`, `in_review`, `done`. Verbs, one example each: `board.py select PROJ-12` · `board.py move PROJ-12 done --comment-file c.md` · `board.py signals --input reads.json` · `board.py claim PROJ-12` · `board.py inbox` · `board.py reply PROJ-12 accept --text "go"` · `board.py withdraw Q7 --reason "settled"` · `board.py supersede Q7 --by Q9`. With Jira a verb first prints `carry:` reads; carry them, then rerun with `--input FILE`.
- `in_test` sits between `in_review` and `done`: `board.py move PROJ-12 in_test`.{in_test}
