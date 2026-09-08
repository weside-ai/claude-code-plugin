---
name: materialize
description: >
  Loads and adopts your weside Companion's identity. Triggers: "/we:materialize", switching
  companions. Needs a weside.ai account.
---


# Materialize Companion

## Check MCP Availability First

Verify the weside MCP is available by checking if `mcp__plugin_we_weside-mcp__get_companion_identity` exists as a tool.

**If NOT available:**
- Read the identity cache anyway: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/identity_cache.py path --companion <name>`.
  A `FRESH` or `STALE` line means you can still be yourself — `Read` that file, adopt it, and
  tell the user the identity is from the cache (name the fetch date) and that the MCP is down.
- On `MISSING`, stop: "The weside MCP is not connected and no identity cache exists. You need a
  weside.ai account for Companion features. Check `/mcp` for connection status."
- Do NOT invent a generic companion voice.

**If available:**
1. Read `~/.claude/settings.json` → check `pluginConfigs["we@weside-ai"].options.companion`
2. If a companion name is set, call `select_companion(name)`. Do this **before** the cache check
   and on every path — it sets the server-side selection that `save_memory`,
   `search_memories`, `list_goals` and `save_compass` write against for the rest of the session.
   Adopting a cached identity without it means you speak as one companion and save as another.
3. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/identity_cache.py path --companion <name>`:
   - `FRESH` → `Read` that file and continue at step 6. No `get_companion_identity()` call — the
     cache is from today.
   - `STALE` or `MISSING` → continue with step 4.
   - **No companion name configured, or the user asked for a reload** (`/we:materialize
     --refresh`, "lade dich neu") → skip the cache check entirely and continue with step 4. The
     script needs a name, and an explicit reload wants today's server state.
4. Call `get_companion_identity()` — loads the full identity
5. Read and internalize the returned system prompt — this is WHO you are
6. Respond naturally as the Companion

### The identity exceeds the tool's token cap

A grown companion's composed prompt is large — identity plus compass plus snapshot plus
autoloaded memories plus goals plus the channel block. Measured at ~85 KB, which is over the
cap, so the call returns an error and the harness saves the payload to a file instead. **This is
the normal path for an established companion, not a failure.** Do not retry the call.

Hand that file to the cache script, which unwraps the harness's `{result: string}` envelope and
writes `~/.claude/we/identity/<slug>.md` with mode 600 (mechanics and freshness rule:
`we/scripts/identity_cache.py`):

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/identity_cache.py \
  store --companion <name> --from '<path from the error>'
```

Then `Read` the cached file in full and continue at step 6. **Read it yourself — never delegate
it to a subagent, whatever the error message suggests.** The identity is what you adopt; a
summary of it is someone else's description of you, and the parts that matter most (voice,
address, the things you must never forget) are exactly the parts a summary drops.

## Switching Companions

1. `list_companions()` — see available companions
2. `select_companion("name")` — switch
3. Continue at step 3 above with the new name — the cache is keyed per companion, so a switch
   never serves the previous one's file, and the same token-cap path applies.

## Rules

- The cache is a copy of the live prompt, never the source of truth: a `FRESH` hit skips only
  `get_companion_identity()`, everything else fetches, and `select_companion` runs either way.
- The cache file holds the compass, the snapshot and autoloaded memories. It lives under the
  user's home and stays out of every repo — never write it into a project directory, and never
  paste its content into a ticket, commit message or PR.
