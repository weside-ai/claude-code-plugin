# Saga template

The file is `docs/plans/<saga>-saga.md`. Frontmatter values and the mirror block format:
`references/apo-hierarchy.md` § Links between altitudes and § Mirror block.

```markdown
---
type: saga-plan
saga: <saga-slug>
vision: <vision-slug or null>
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft
---

# Saga: <Name>

## The Bet

<One sentence.>

## Why Now

<2–4 sentences: what in the Vision, the market or the codebase makes this the next bet.>

## Success Criteria

- <Externally verifiable.>

## In Scope

- <What this Saga covers.>

## Out of Scope

- <What it does not cover. Never empty.>

## What Success Eliminates

<"If this lands, we no longer argue about X.">

## Sub-Epics

<mirror block: child Epics>

## Open Questions

- <Genuinely unsettled; fodder for /we:meet saga.>

## Updates Log

- YYYY-MM-DD — created

## Notes

<ADRs, prior decisions, market context.>
```
