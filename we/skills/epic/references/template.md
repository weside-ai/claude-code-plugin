# Epic template

The file is `docs/plans/<epic>-epic.md`. Frontmatter values and the mirror block format:
`references/epic-plan.md` § Links and § Mirror block. `serves:` and `fence:` (where the
epic's stories may write) follow `references/story-plan.md` § What the Ready gate reads. `/we:plan-story` and `/we:master`
read `## Success Criteria` and `## Scope`: keep both headings verbatim.

```markdown
---
type: epic-plan
epic: <epic-slug>
ticket: <KEY or null>
serves: <metric of the goal file>; <metric>
fence: [<glob>, <repo>:<glob>]
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft
---

# Epic: <Name>

## Why

<3–6 sentences, narrative: why the Epic exists, which goal-file metric it moves, who feels the
change. A refiner reads this first.>

## Scope

**IN:**

- <Concrete deliverable>

**OUT:**

- <Explicitly excluded: the first cut if the slice runs long>

## Target architecture

<The seam, the new primitive, the migration shape. References to ADRs and primitives.>

## Sequencing

<Risk-driven order, the rough Stories with acceptance shape, what gets cut first, the first Story.>

## Dependencies

- <Other Epic, infrastructure, external service, open decision>

## Stories

<mirror block: child Stories>

## Success Criteria

<What shipped, what a user can do that they could not before, what telemetry confirms it.>

## Open Questions

- <What the drafting could not settle; each becomes one decision story (L0 §Units).>

## Orchestration contract

<Binding for every `/we:master` run on this Epic; the Lead asks only what it leaves open.>

- **Rebuilding the context**, in this order: this file; git, PRs and tickets for the Epic's keys;
  the state table per `/we:master` § State per story; the next Story's plan only.
- **Upkeep after each event**, committed before the next Story: plan on main (Selected) → mirror row +
  Updates Log; PR merged → mirror, Updates Log, Learnings forward into the next plan; question
  answered → answer where it applies, with who and when; Story re-cut → `## Sequencing` + mirror.
- **Standing permissions:** <auto-merge per the table in `/we:master` § Close the run; delegations to other sessions, secrets>.
- **Staging RCs:** per L0 §Release (the RC train job; by hand while the repo has none: <who cuts it, with
  <the repo's release verb>>). Prod releases stay with the owner.
- **Staging verification:** as soon as the RC is live, an agent runs every step a test account can observe
  (API, logs, DB reads); the owner gets only what needs eyes (the look of a surface, a device).
- **Stops for the owner:** <destructive operations with a count, product questions, money beyond the plan, uncertainty>.

## Updates Log

- YYYY-MM-DD — created

## Notes

<ADRs, prior decisions, design context.>
```
