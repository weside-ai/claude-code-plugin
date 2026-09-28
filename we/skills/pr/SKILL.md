---
name: pr
description: >
  Opens the PR for the current branch: merge the base, push once, body with ticket, AC evidence and
  the plan's verification receipt, ticket to In Review. Triggers: "/we:pr", "open the PR".
---

# /we:pr

For a branch built outside `/we:orchestrate`; orchestrate § Push, PR, CI does the same inside a run.

1. Run the repo's static gates and the affected tests by name first; red → stop and report.
2. `git fetch && git merge origin/<base>` (never rebase: that needs a force-push, the user's call).
   A conflict goes to the user. Then `git push -u origin <branch>` once.
3. Body in a file, passed as `--body-file` (a `--body "$(…)"` cannot be read by the verification
   hook): summary, the ticket key on its own line, AC → evidence, and the `## Verification` block
   copied verbatim from `docs/plans/<KEY>-story.md`. Never write that block yourself: no block in the
   plan means verification did not happen, so say so and stop. A hook refusal for a wrong flag or an
   unreadable file is fixed once; a second refusal is reported verbatim.
4. `gh pr create --title "<KEY>: <summary>" --body-file <file>`. Ticket: link the PR, move it to In
   Review and read the status back (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`); never to Done.
5. Report the URL. Red CI or review findings → `/we:ci-review <PR>`. Merging is the user's.
