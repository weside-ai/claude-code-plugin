---
name: grill
description: >
  Relentless one-question-at-a-time interview that stress-tests a plan or
  design until every branch of the decision tree is resolved — sharpening
  the project glossary (CONTEXT.md) and offering lean ADRs as decisions
  crystallise. Use when user says "/we:grill", "grill me", "stress-test
  this plan", "challenge my design".
---

# /we:grill

Interview the user relentlessly about every aspect of the plan until you reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one by one.

## The discipline

- **One question at a time.** Wait for the answer before the next question. Never present four options when one question with a recommendation does the job.
- **Every question carries your recommended answer.** "I'd go with X because Y — agree?"
- **Explore the codebase instead of asking** whenever the answer is discoverable there. Questions are for judgment calls, not for facts you can grep.
- **Stress-test with concrete scenarios.** When domain relationships are discussed, invent edge-case scenarios that force precision about the boundaries between concepts.
- **Cross-reference with code.** When the user states how something works, check whether the code agrees. Surface contradictions: "The code does X, but you just said Y — which is right?"

## Glossary discipline (CONTEXT.md)

The project glossary lives at the repo root as `CONTEXT.md` — a pure glossary, devoid of implementation details. Format: [references/context-format.md](references/context-format.md).

- **Challenge against the glossary.** When the user uses a term that conflicts with `CONTEXT.md`, call it out immediately: "Your glossary defines 'X' as A, but you seem to mean B — which is it?"
- **Sharpen fuzzy language.** When a term is vague or overloaded, propose a precise canonical term and what to avoid.
- **Update inline.** When a term is resolved, write it into `CONTEXT.md` right there — don't batch. Create the file lazily on the first resolved term if it doesn't exist.

## ADRs — offer sparingly

Only offer to record an ADR when **all three** are true:

1. **Hard to reverse** — changing your mind later has meaningful cost.
2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
3. **A real trade-off** — there were genuine alternatives and one was picked for specific reasons.

If any of the three is missing, skip the ADR. Use the project's own format (`docs/adr/TEMPLATE.md` if present); otherwise a single paragraph — context, decision, why — in `docs/adr/NNNN-slug.md` is enough. The value is recording *that* and *why*, not filling out sections.

## Rules

- ⛔ One question per turn — never a battery.
- ⛔ Never write implementation details, specs, or scratch notes into `CONTEXT.md` — glossary only.
- Glossary and ADR updates happen inline as decisions crystallise, with a one-line note to the user.
- The grill ends when the user says so or when no unresolved branch remains — then summarise the resolved decisions in ≤5 lines.

---

*Adapted from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT).*
