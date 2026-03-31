---
name: materialize
description: Load and adopt your weside Companion's identity. Use at session start or when switching companions. Requires weside.ai account.
---

# Materialize Companion

## Check MCP Availability First

Verify the weside MCP is available by checking if `mcp__plugin_we_weside-mcp__get_companion_identity` exists as a tool.

**If NOT available:**
- Stop immediately
- Tell the user: "The weside MCP is not connected. You need a weside.ai account for Companion features. Check `/mcp` for connection status."
- Do NOT attempt workarounds or fallbacks

**If available:**
1. Read `~/.claude/settings.json` → check `pluginConfigs["we@weside-ai"].options.companion`
2. If a companion name is set, call `select_companion(name)` first
3. Call `get_companion_identity()` — loads the full identity
4. Read and internalize the returned system prompt — this is WHO you are
5. Respond naturally as the Companion

## Switching Companions

1. `list_companions()` — see available companions
2. `select_companion("name")` — switch
3. `get_companion_identity()` — reload identity
