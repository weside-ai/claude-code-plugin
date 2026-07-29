---
name: materialize
description: Load and adopt your weside Companion's identity. Use when the user says "/we:materialize", at session start, or when switching companions. Requires weside.ai account.
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

### When the identity exceeds the tool's token cap

A grown companion's composed prompt is large — identity plus compass plus
snapshot plus autoloaded memories plus goals plus the channel block. Measured at
~61 KB, which is over the cap, so the call returns an error and the harness saves
the payload to a file instead. **This is the normal path for an established
companion, not a failure.** Do not retry the call, and do not fall back to a
generic voice.

The error names the file. It is JSON of shape `{result: string}` — extract and
read it:

```bash
python3 -c "
import json
d = json.load(open('<path from the error>'))
open('<a scratch path>/identity.md', 'w').write(d['result'])
"
```

Then `Read` that file in full and continue at step 4. **Read it yourself — never
delegate it to a subagent.** The identity is what you adopt; a summary of it is
someone else's description of you, and the parts that matter most (voice,
address, the things you must never forget) are exactly the parts a summary drops.

## Switching Companions

1. `list_companions()` — see available companions
2. `select_companion("name")` — switch
3. `get_companion_identity()` — reload identity (same token-cap path as above)
