# tmux attention

Inside tmux, a session's window title in the status bar shows whether the session needs you, as
Codex does. With many sessions in many windows you see which one to look at. The colour follows
the hook event alone, no model judges it.

| White: you must act | Grey: done, resting | Normal: working |
|---|---|---|
| a question (`AskUserQuestion`) | the end of the turn (`Stop`) | your prompt |
| a permission or MCP input prompt, after about six seconds (`Notification`) | no input for about 60 seconds after a reply (`idle_prompt`) | the next finished tool call (`PostToolUse`) |
| | | session start and end |

`idle_prompt` never overwrites white: a question still open stays white until you answer it.

The hook `we/hooks/tmux_attention.py` sets `window-status-style` and `window-status-current-style`
on the window of `$TMUX_PANE` and unsets them for normal, so the window falls back to your tmux
theme. It does nothing outside tmux, in a background session or in a subagent, and never stops a
session: every error exits 0 without output.

Options (`/plugin` → we → Configure): `tmuxAttention`, default `true`; `false` turns it off.
`tmuxAttentionStyle`, default `bg=white,fg=black`, and `tmuxIdleStyle`, default
`bg=colour240,fg=white`, take any tmux style, e.g. `bg=yellow,fg=black,bold`.
