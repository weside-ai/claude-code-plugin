---
description: Intelligently update project documentation
---

# Documentation Manager

**Usage:**

- `/docs` — Auto-detect and update changed documentation
- `/docs "Added Docker multi-environment setup"` — With context hint

Use the Agent tool to launch the doc-manager agent:

```
Agent(
    subagent_type="we:doc-manager",
    description="Update project documentation",
    prompt="Update documentation. Context: $ARGUMENTS",
    run_in_background=True
)
```

**Note:** Agent runs in background. You'll be notified when it completes.
