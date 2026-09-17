---
name: session-name-reference
description: One name for the session and its tmux window, set whenever the window's purpose changes. Owner — referenced by /we:orchestrate, /we:story, /we:standup.
---

# The session's name is its purpose, and the window shows it

A human with ten windows open re-learns what each one does by its name. Two names exist
and they drift: Claude Code's session name (set with `/rename`) and the tmux window
title. Measured 2026-09-17 in a session named `redesign` whose tmux window still read
`infra` — the user had been keeping the two in step by hand.

**Whenever the window's purpose changes** — a story is loaded, an epic run boots, a
close-out ends — set the name. Short, one token, what the window IS: the ticket key
(`WA-2284`) or one word for the epic (`design-v2`). Never a sentence.

## The tmux half is yours

```bash
[ -n "$TMUX_PANE" ] && tmux rename-window -t "$TMUX_PANE" "<name>" 2>/dev/null
```

`$TMUX_PANE` is the pane this Claude runs in — the Bash tool inherits it. Outside tmux the
guard makes this a no-op. Never rename by window index or by a name you guessed; the pane id
is the only address that cannot hit another session's window.

## The Claude half is the user's — hand it over as one line

`/rename` is a slash command and no tool runs it. So after renaming the window, print the
exact line for the user to paste, and nothing else about it:

```
/rename <name>
```

Print it once per purpose change, not per turn.
