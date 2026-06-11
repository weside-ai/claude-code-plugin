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

## Full teardown (after `TeamDelete`)

`TeamDelete` removes only team metadata; a done/idle member's agent process and tmux pane survive (ghost members in tmux). Order:

1. Send shutdown message to every member (`SESSION COMPLETE — you may stop.`)
2. `TeamDelete()`
3. `pkill -f -- "--team-name <team_name>"` — kills this team's agent procs via argv (precise)
4. `tmux kill-pane` the leftover idle panes (`tmux list-panes -a` to find them; skip the lead's own)

If `TeamDelete` fails because a member is still finishing: wait 30 s, retry twice, then warn and continue — the user already has their result.
