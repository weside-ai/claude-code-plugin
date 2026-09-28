# Glossary format (`CONTEXT.md`)

Used only when a repo has no glossary yet. A pure glossary at the repo root: never a spec, a scratch pad or a home
for implementation decisions.

```md
# {Context name}

{One or two sentences: what this context is and why it exists.}

## Language

**Order**:
A request to purchase, from placement to fulfilment.
_Avoid_: Purchase, transaction
```

- **Be opinionated.** Several words for one concept → pick the best, list the others under `_Avoid_`.
- **Tight definitions.** One or two sentences; what the term IS, not what it does.
- **Project terms only.** General programming concepts stay out, however often they are used.
- **Group under subheadings** when clusters emerge; a flat list is fine otherwise.
- **Several bounded contexts** (rare): a `CONTEXT-MAP.md` at the root lists each context's `CONTEXT.md` and how
  they relate. Infer which context the topic belongs to; ask when unclear.

---

*Adapted from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT).*
