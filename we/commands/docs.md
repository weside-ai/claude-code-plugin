---
description: Documentation coherence steward — delegates to doc-architect agent
---

# /we:docs — Documentation Architect

**Usage:**

- `/we:docs Where is memory versioning documented?`
- `/we:docs I added a dedup pattern for webhooks — where does it go?`
- `/we:docs I changed app/db/session.py — what docs need updating?`
- `/we:docs Scan architecture/ for drift`
- `/we:docs Refresh the bypass register`

**User Input:** $ARGUMENTS

Invokes the `doc-architect` agent via the `/we:docs` skill. The agent reads
the doc landscape fresh on every invocation (rules, indices, tree) and
answers the user's request in one of 5 modes: question, classify, integrate,
audit, or register.

**Never writes autonomously** — every file change requires explicit approval.

```python
Agent(
    subagent_type="we:doc-architect",
    description="Doc architect: handle documentation request",
    prompt="$ARGUMENTS",
    run_in_background=False,
)
```

**References:**

- Skill: `we/skills/docs/SKILL.md`
- Agent: `we/agents/doc-architect.md`
- Legacy (deprecated): `we/agents/doc-manager.md` — now a thin delegate to `doc-architect`
