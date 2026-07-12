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
BLOCKING/PASS verdict. It never hunts bugs — for that, Codex adversarial-review (Claude wrote the
code) or Claude's native `/code-review` (anything else) runs separately; see
`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md` § Bug-hunt dispatch.
