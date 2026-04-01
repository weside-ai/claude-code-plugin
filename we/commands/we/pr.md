---
description: Create Pull Request with prerequisite validation
---

# PR Creator

**User Input:** $ARGUMENTS

Launch the pr-creator agent:

```python
Agent(subagent_type="we:pr-creator", prompt="Create a PR for the current branch. $ARGUMENTS")
```
