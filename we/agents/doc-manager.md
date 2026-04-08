---
name: doc-manager
description: DEPRECATED — use doc-architect agent via /we:docs instead. This agent remains only as a thin delegate for backwards compatibility with existing pipeline invocations. Scheduled for removal once all call sites migrate.
color: gray
---

# Doc Manager (DEPRECATED)

**Status:** DEPRECATED. Use `doc-architect` via `/we:docs`.

**Why deprecated:** The original `doc-manager` was built on a "KNOW, don't
SEARCH" mental model that baked the doc tree structure into the agent prompt.
That works for the minute it was written, then rots. `doc-architect`
replaces it with a fresh-boot model: on every invocation, the agent reads
the rules and the tree fresh, so the mental map is always current.

## Migration

All existing call sites should migrate to:

```python
Agent(
    subagent_type="we:doc-architect",
    description="Doc architect: <short summary>",
    prompt="<task>",
    run_in_background=False,
)
```

Or equivalently via the `/we:docs` skill.

## Legacy behaviour (if still invoked)

If this agent is invoked directly, delegate to `doc-architect` with the
same prompt:

1. Read the user's request
2. Invoke `we:doc-architect` with the request verbatim
3. Return the `we:doc-architect` response

Do NOT execute the old "know the tree" logic — it will produce stale
answers.

## References

- **Replacement:** `we/agents/doc-architect.md`
- **Entry point:** `/we:docs` (`we/skills/docs/SKILL.md`)
