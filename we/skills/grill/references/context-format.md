# CONTEXT.md Format

The project glossary at the repo root. A pure glossary — never a spec, scratch pad, or home for implementation decisions.

## Structure

```md
# {Context Name}

{One or two sentences: what this context is and why it exists.}

## Language

**Order**:
A request to purchase, from placement to fulfilment.
_Avoid_: Purchase, transaction

**Customer**:
A person or organization that places orders.
_Avoid_: Client, buyer, account
```

## Rules

- **Be opinionated.** When multiple words exist for the same concept, pick the best one and list the others under `_Avoid_`.
- **Keep definitions tight.** One or two sentences max. Define what it IS, not what it does.
- **Only project-specific terms.** General programming concepts (timeouts, error types, utility patterns) don't belong, even if used extensively.
- **Group under subheadings** when natural clusters emerge; a flat list is fine otherwise.
- **Create lazily.** No `CONTEXT.md` yet → create it when the first term is resolved.

## Multi-context repos (rare)

A repo with several bounded contexts puts a `CONTEXT-MAP.md` at the root listing each context's `CONTEXT.md` location and the relationships between them. Infer which context the current topic belongs to; ask if unclear.

---

*Adapted from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT).*
