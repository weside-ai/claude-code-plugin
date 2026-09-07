---
description: AC-alignment and DoD check with verdict
---

# AC Review

**User Input:** $ARGUMENTS

Launch the ac-reviewer agent:

```python
Agent(subagent_type="we:ac-reviewer", prompt="Review the current changes. $ARGUMENTS")
```

This checks the diff against the Story's acceptance criteria and the DoD, then writes the
BLOCKING/PASS verdict. It never hunts bugs — that is the repo's CI review gates' job, on the PR;
see `${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md` § Bug-hunt.
