# Orchestration facts of this repo

`/we:setup` wrote this file for a repo with a crew. `/we:master`, `/we:develop`, `/we:merged`,
`/we:ci-review` and the plan commit read it; each heading below is a section one of them names.
Replace every `TODO` line with this repo's fact, or with `none` and why.

## Bootstrap

TODO: the command a fresh worktree runs before its first gate, and how to check it worked.

## Generated artifacts

TODO: files a change must regenerate and commit (API spec, clients, lock files), with the command.

## Baselines

TODO: gate baselines a builder must not touch (coverage, size ratchets), and who updates them.

## Risk-class files

The merge hook classifies every PR from `.weside/risk-paths` (or the crew's `risk.command`) on the
default branch. A repo with a crew and neither refuses every merge. TODO: name who owns the rules.

## Ticket states

TODO: this repo's ticketing status names for idea, backlog, selected, in progress, in review, done.

## Where plan commits land

TODO: how a plan or doc commit reaches the default branch (a PR, a docs script, a direct push).

## Host resources

TODO: shared ports, databases or locks that two workers on one host must not take at once.

## Close-out after a merge

TODO: what runs after a merge (an environment repair, a worktree or database cleanup), or `none`.
