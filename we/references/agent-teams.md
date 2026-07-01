# Agent Teams — Prerequisite + Teardown

## Env flag (prerequisite)

Live teams (council members, builder-teammates) require Claude Code's experimental Agent Teams feature in `~/.claude/settings.json`:

```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

A session restart is needed after toggling. `/we:setup` Step 5.0 sets the flag on request. If the flag is missing at run time, **abort with this remediation hint** — never fall back to a non-team flow:

```text
This skill needs Agent Teams enabled.

Add this to ~/.claude/settings.json:
  { "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
Then restart your session. Or run /we:setup — it sets the flag for you.
```

## The implicit team (current harness API)

There is no `TeamCreate`/`TeamDelete` tool and no `team_name` parameter — every session already
has a single implicit team. Members join it just by being spawned:

```python
Agent(name=<role-slug>, subagent_type=<...>, model="sonnet", description=<...>, prompt=<brief>)
```

- **Never pass `team_name`** — the parameter no longer exists; drop it from any spawn call or brief text that still carries it.
- Once spawned, a member is addressable by `name` from any other session (lead or teammate) via `SendMessage(to=<name>, message=..., summary=...)` — no separate join step.
- **All member spawns still go in one assistant message** — that is what makes them initialize concurrently and start hearing each other from message 1. This rule is unchanged by the API change.

## Full teardown (mandatory, even on failure paths)

There is no `TeamDelete` — teardown means asking each member to stop, verifying they did, and
cleaning up anything that didn't. Order:

1. **Shutdown message to every member** (including any recorded as absent/blocked — idempotent):
   `SendMessage(to=<member-name>, message="SESSION COMPLETE — you may stop.", summary="shutdown_request")`
2. **Verify termination** — confirm each member actually stopped (no further activity / task
   marked complete) before moving on. Do not assume the message alone did it.
3. **Fallback: `TaskStop(<member-name>)`** for any member that doesn't terminate on its own
   within a short wait.
4. **Check for leftover tmux panes** — `tmux list-panes -a` to find any pane still attached to a
   member's session; `tmux kill-pane` the leftover idle ones. Skip the lead's own pane.

If a member is still finishing genuine work when teardown starts: wait 30 s, retry the shutdown
message + verify once more, then fall back to `TaskStop` rather than waiting indefinitely.

**Always tear down — even on failure paths.** A leaked member blocks the next council/orchestrate
run in the same session and keeps consuming resources in the background.
