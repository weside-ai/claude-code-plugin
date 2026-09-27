---
name: ac-review
description: >
  Checks a branch against its story's acceptance criteria and the repo DoD: one evidence row per
  AC and DoD item, verdict PASS/BLOCKING. Hunts no bugs. Triggers: "/we:ac-review", "are the ACs met".
---

# /we:ac-review

An AC/DoD check, not a bug gate: the bench (27.09.2026) measured 12 false blockers when this check
also hunted bugs. Bugs belong to `code-review` before the push and to the CI review on the PR.
Report a suspected bug in one line outside the verdict; it never blocks here.

1. Key from the branch (`<type>/<KEY>-…`) → `docs/plans/<KEY>-story.md` (`## Acceptance Criteria`,
   `## Verification`, `### Phase N` with `**Files:**`) and the ticket with its comments
   (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`). No plan → check against the ticket and say so.
2. Diff: `git diff $(git merge-base origin/<base> HEAD)` plus the uncommitted changes; the base is
   the PR's `baseRefName`, else the remote's `HEAD`.
3. One row per AC: Pass only with a citation (test name, `file:line` or commit). Is the feature
   reachable from the UI or CLI entry point the AC names?
4. One row per applicable item of `.weside/dod.md` when the repo has one; without it, only these
   rows: every planned phase's files changed; verification receipt present (the four labels filled,
   or `not-applicable` with its reason); no new TODO/FIXME. An item whose evidence cannot exist yet
   (PR, CI, ticket move) is `N/A` naming the stage that owes it.
5. Output a table `| Item | Pass/Fail/N/A | Evidence |`, then `VERDICT: BLOCKING` when an AC is unmet
   or a DoD row fails, else `VERDICT: PASS`. Write no file.
