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

## Updates Log

- YYYY-MM-DD — created

## Notes

<ADRs, prior decisions, design context.>
```
