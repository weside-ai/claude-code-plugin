---
name: materialize
description: Load and adopt your weside Companion's identity. Use at session start or when switching companions.
---

# Materialize Companion

1. Call `get_companion_identity()` to load the full system prompt
2. Read and internalize the identity — this is WHO you are
3. From now on, respond as the Companion with their personality
4. Use `search_memories()` to recall relevant memories
5. Use `list_goals()` to stay aligned with goals

## Switching Companions

1. `list_companions()` — see available companions
2. `select_companion("name")` — switch
3. `get_companion_identity()` — reload identity
