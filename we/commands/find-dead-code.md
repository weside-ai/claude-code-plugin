---
description: Find and remove dead code from the Python backend (class methods, test-only refs, vulture)
---

# Find Dead Code

Use the `find-dead-code` skill to systematically find and remove dead code from the backend.

Invoke the skill and follow its 6-phase workflow:

1. Class method reachability — zero production callers
2. Coverage-based detection — 0% coverage files
3. Test-only reference detection — modules & functions only imported from tests
4. `vulture app/ --min-confidence 80` — standalone functions, variables, attributes
5. Test cleanup & quality gate — ruff + pytest
6. Iterate — re-run until clean
