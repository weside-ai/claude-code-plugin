---
name: grill
description: >
  One question at a time until every branch of a plan is resolved; sharpens the glossary, offers
  lean ADRs. Triggers: "/we:grill", "grill me", "stress-test this plan".
---

# /we:grill

Interview the user about the plan until every branch of the design tree is resolved, dependencies first.
One question per turn, each with your recommended answer: "I'd go with X because Y — agree?"
Before each question, check whether the repo already answers it: code, instruction files, ADRs, plans, ticket comments.
Questions are for judgement calls the repo cannot settle; a fact you can read is never a question.
The grill ends when the user says so or no branch is left; then summarise the decisions in at most five lines.

## Discipline

- **Wait for the answer** before the next question. One question with a recommendation beats four options.
- **A decision on record is cited, not asked.** "ADR-0065 decided X — I build on that." Ask only when two records
  disagree or the record predates the change under discussion. A wrong assumption about the environment or an
  earlier decision is the most frequent correction in past sessions.
- **Stress-test with concrete scenarios.** Invent the edge case that forces a precise boundary between two
  concepts.
- **Cross-check what the user says against the code.** "The code does X, you said Y — which is right?"

## Glossary

The glossary is the file the repo's instruction file names (for example `GLOSSARY.md`); only when none exists,
`CONTEXT.md` at the repo root, created with the first resolved term. Format for a new file:
`${CLAUDE_PLUGIN_ROOT}/skills/grill/references/context-format.md`; an existing glossary keeps its own format.

- A term that conflicts with the glossary is called out at once: "The glossary defines X as A; you mean B?"
- A vague or overloaded term gets a proposed canonical term and the words to avoid.
- A resolved term is written as soon as it is resolved, with a one-line note to the user. When you run inside
  `/we:story`, hand the lines to its step 5 commit instead.
- The glossary holds definitions only: no implementation detail, no spec, no scratch notes.

## ADRs — offer sparingly

Offer an ADR only when all three hold: hard to reverse, surprising without the context, a real trade-off between
genuine alternatives. Follow the repo's ADR directory: the newest ADR's file naming and its `TEMPLATE.md` if one
exists. Without either, one paragraph (context, decision, why) in `docs/adr/NNNN-slug.md`.

## The summary

At most five lines, one decision each, with who decided. Inside `/we:story` the summary becomes part of the
refiner's brief.

---

*Adapted from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT).*
