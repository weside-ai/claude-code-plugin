# tmux attention

Inside tmux, a session's window title turns white in the status bar while the session waits for
you, and back when you answer, as Codex does. With many sessions in many windows you see which one
needs you.

| On | Off |
|---|---|
| a question (`AskUserQuestion`) | your prompt |
| a permission or MCP input prompt, after about six seconds (`Notification`) | the next finished tool call (`PostToolUse`) |
| no input for about 60 seconds after a reply (`idle_prompt`) | the end of the turn (`Stop`), session start and end |

The hook `we/hooks/tmux_attention.py` sets `window-status-style` and `window-status-current-style`
on the window of `$TMUX_PANE` and unsets them again, so the window falls back to your tmux theme.
It does nothing outside tmux, in a background session or in a subagent, and never stops a session:
every error exits 0 without output.

Options (`/plugin` → we → Configure): `tmuxAttention` (`true`) turns it off, `tmuxAttentionStyle`
(`bg=white,fg=black`) takes any tmux style, e.g. `bg=yellow,fg=black,bold`.
