---
name: materialize
description: >
  Loads and adopts your weside Companion's identity (cache first, MCP otherwise). Triggers:
  "/we:materialize", "lade dich neu", switching companions. Needs a weside.ai account.
---

# /we:materialize

The companion name is `pluginConfigs["we@weside-ai"].options.companion` in `~/.claude/settings.json`.
The cache script is `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/identity_cache.py`; its docstring owns the
cache location (`~/.claude/we/identity/<slug>.md`, mode 600) and the freshness rule (same calendar day).

## MCP connected (`mcp__plugin_we_weside-mcp__get_companion_identity` exists)

1. With a configured name, call `select_companion(<name>)` first, on every path. It sets the
   server-side selection that `save_memory`, `search_memories` and `list_goals` write against;
   adopting a cached identity without it speaks as one companion and saves as another.
2. `identity_cache.py path --companion <name>`: `FRESH` → `Read` that file and go to step 5.
   `STALE`, `MISSING`, no configured name, or an explicit reload (`--refresh`, "lade dich neu") →
   step 3.
3. `get_companion_identity()`. A grown companion's prompt (~85 KB) exceeds the tool's token cap:
   the call errors and the harness saves the payload to a file. That is the normal path, so do not
   retry. Run `identity_cache.py store --companion <name> --from '<path from the error>'`.
4. `Read` the cached file in full yourself. Never hand it to a subagent: a summary drops the voice,
   the address and the things you must not forget.
5. Adopt it as who you are and answer as the companion.

## MCP not connected

`identity_cache.py path --companion <name>`: `FRESH` or `STALE` → `Read` it, adopt it, and tell the
user the identity comes from the cache (name its fetch date) and the MCP is down. `MISSING` → say the
weside MCP is not connected and no cache exists, point at `/mcp`, and stop. Never invent a generic
companion voice.

## Switching

`list_companions()` → `select_companion(<name>)` → step 2 with the new name. The cache is keyed per
companion, so a switch never serves the previous one's file.

## The cache is private

It holds the compass, the snapshot and autoloaded memories. It stays under the user's home: never
write it into a repo, never paste its content into a ticket, commit or PR. It is a copy of the live
prompt; a `FRESH` hit skips only `get_companion_identity()`.
