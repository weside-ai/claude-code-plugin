---
description: Professional code review with AC alignment
---

# Code Review

**User Input:** $ARGUMENTS

Launch the code-reviewer agent:

```python
Agent(subagent_type="we:code-reviewer", prompt="Review the current changes. $ARGUMENTS")
```

Standalone `/we:review` runs the **full** review — bugs plus AC-alignment plus the DoD Quick Check —
because there is no AC+DoD gate ahead of it. (Inside `/we:build`, Step 3 already gates AC + DoD and
passes `DOD_AND_AC_ALREADY_VERIFIED`, so the agent reviews for bugs only. Do not pass that token here.)
