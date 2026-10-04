# Epic template

The file is `docs/plans/<epic>-epic.md`. Frontmatter values and the mirror block format:
`references/apo-hierarchy.md` § Links between altitudes and § Mirror block. `/we:story`, `/we:refine`
and `/we:orchestrate` read `## Success Criteria` and `## Scope`: keep both headings verbatim.

```markdown
---
type: epic-plan
epic: <epic-slug>
saga: <saga-slug or null>
ticket: <KEY or null>
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft
---

# Epic: <Name>

## Vision

<3–6 sentences, narrative: why the Epic exists, which part of the Saga it delivers, who feels the
change. The decomposition meeting reads this first.>

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

- <What Solo could not settle; fodder for /we:meet epic.>

## Orchestration contract

<Binding for every `/we:orchestrate` run on this Epic; the Lead asks only what it leaves open.>

- **Rebuilding the context**, in this order: this file; git, PRs and tickets for the Epic's keys;
  the state table per `/we:orchestrate` § State per story; the next Story's plan only.
- **Upkeep after each event**, committed before the next Story: plan approved → mirror row +
  Updates Log; PR merged → mirror, Updates Log, Learnings forward into the next plan; question
  answered → answer where it applies, with who and when; Story re-cut → `## Sequencing` + mirror.
- **Standing permissions:** <auto-merge (armed after `/we:ci-review` green; a non-destructive migration auto-merges serially: the second PR merges `origin/<default>` after the first lands, then arms; money paths and destructive migrations stay user merge), delegations to other sessions, secrets>.
- **Staging RCs:** the Lead tags one with <the repo's release verb> without asking once a merged batch
  needs staging verification, at most one RC per batch, and says so in its status line. Prod releases stay with the owner.
- **Staging verification:** as soon as the RC is live, an agent runs every step a test account can observe
  (API, logs, DB reads); the owner gets only what needs eyes (the look of a surface, a device).
- **Stops for the owner:** <destructive operations with a count, product questions, money beyond the plan, uncertainty>.

## Updates Log

- YYYY-MM-DD — created

## Notes

<ADRs, prior decisions, design context.>
```
