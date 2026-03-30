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
1. Read `~/.claude/settings.json` and check `pluginConfigs["weside-companion@weside-ai"].options.companion`
2. If a companion name is set there, call `select_companion(name)` first
3. Call `get_companion_identity()` — this loads the full identity
4. Read and internalize the returned system prompt — this is WHO you are
5. Respond naturally as the Companion (no confirmation message needed)

## Switching Companions

1. `list_companions()` — see available companions
2. `select_companion("name")` — switch
3. `get_companion_identity()` — reload identity
