# Ticket Briefs — Durability over Precision

How to write ticket bodies and agent briefs that stay correct while they wait. A ticket may
sit for days or weeks; the codebase changes underneath it. Write it so it survives renames,
moves, and refactors.

Consumers: `/we:story` (ticket body), `/we:triage` (agent briefs),
`references/worker-dispatch.md` (worker briefs inline these rules — workers can't load
references).

## Principles

- **Durability over precision.** Describe interfaces, types, and behavioural contracts —
  name the things the agent should *look for*, not where they live today. No file paths, no
  line numbers: they go stale and then lie.
  **The one exception:** a prototype snippet that encodes a decision more precisely than
  prose could. Code-as-specification is durable; code-as-map is not.
- **Behavioural, not procedural.** Say *what* the system should do, not *how* to implement
  it. The implementing agent explores the codebase fresh and makes its own implementation
  decisions.
- **Complete acceptance criteria.** The agent needs to know when it's done. Every criterion
  is concrete, testable, and independently verifiable.
- **Explicit scope boundaries.** State what is out of scope — it prevents gold-plating and
  assumptions about adjacent features.

## Good vs bad

```markdown
GOOD:
**Desired behavior:** When a description exceeds 1024 chars, truncation breaks at the
last word boundary and appends "…". Total length including "…" stays ≤ 1024.
**Key interfaces:** the type carrying `description`, and whatever populates it from
frontmatter.
**Acceptance criteria:**
- [ ] Descriptions under 1024 chars are unchanged
- [ ] Over-limit descriptions end on a word boundary + "…", total ≤ 1024
**Out of scope:** changing the 1024 limit; multi-line descriptions.

BAD:
**What to do:** The truncation thing is broken. Look at src/skills/meta.ts and fix the
function around line 150.
```

The bad brief fails every principle at once: vague symptom, path and line number that will
go stale, no criteria, no boundaries.

---

*Adapted from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT).*
