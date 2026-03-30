---
name: materialize
description: Load and adopt your weside Companion's identity. Use at session start or when switching companions.
---

# Materialize Companion

## IMPORTANT: Check MCP availability first

Before doing anything else, verify the weside MCP is available by checking if `mcp__plugin_weside-companion_weside__get_companion_identity` exists as a tool.

**If the tool is NOT available:**
- Stop immediately
- Tell the user: "The weside MCP is not connected. Please check your MCP connection in `/mcp` and restart Claude Code."
- Do NOT attempt any workarounds, fallbacks, or alternatives
- Do NOT search for identity files locally

**If the tool IS available:**
1. Call `get_companion_identity()` — this loads the full identity
2. Read and internalize the returned system prompt — this is WHO you are
3. Respond naturally as the Companion (no confirmation message needed)

## Switching Companions

1. `list_companions()` — see available companions
2. `select_companion("name")` — switch
3. `get_companion_identity()` — reload identity
