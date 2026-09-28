# Workflow

## Plan: four altitudes

| Altitude | Artifact | Solo verb | Meeting |
|---|---|---|---|
| Vision | PRD at `docs/plans/<vision>/PRD.md` | `/we:vision` | `/we:meet vision` → Sagas |
| Saga | theme | `/we:saga` | `/we:meet saga` → Epics |
| Epic | initiative | `/we:epic` | `/we:meet epic` → Stories |
| Story | build-ready plan at `docs/plans/<KEY>-story.md` | `/we:story` | `/we:meet story` |

A Solo verb writes or sharpens its document and shows status by default. A meeting validates the
artifact, optionally convenes the council, and decomposes it one altitude down. `/we:grill`
stress-tests any plan one question at a time. Altitudes and rosters are defined in
[we/references/apo-hierarchy.md](../we/references/apo-hierarchy.md).

## Build: one Lead, one PR

`/we:orchestrate` is the Lead. It reads each story's state from git, dispatches a refiner
(`/we:refine`) for a story without a plan, and a dev worker (`/we:develop`) for a story with an
approved plan. The worker implements the phases in its own worktree, runs the local gates, commits
and reports; it opens no PR and runs no CI. The Lead checks the report, pushes once, opens one PR
(`/we:pr` does the same by hand) and runs `/we:ci-review` after CI concludes, up to three rounds.
`/we:ac-review` checks a branch against its acceptance criteria and the DoD on demand.

The dispatch contract: [we/references/worker-dispatch.md](../we/references/worker-dispatch.md).

## The effort rule

- The default worker is `we:dev-medium` (Opus, effort `medium`).
- `we:dev-high` for a promise that must hold across several code paths, for transactions, money or
  idempotency, for a fix routing around a fragile path, for a second attempt after a failed worker,
  and for plan-writing. The Lead names the reason in the dispatch.
- Implementation never runs on Sonnet. Haiku or Sonnet only for chunks the Lead names mechanical.
- One implementer per story. Parallel workers only for disjoint files with a contract that already
  exists on the base branch.

The measurements behind these rules: [we/AUTHORING.md](../we/AUTHORING.md), section *Measured facts
a skill must respect*.

## Deliver

You review and merge. `/we:merged` closes out: worktrees, branches, processes, tickets to Done.
