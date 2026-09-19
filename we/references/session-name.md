---
name: session-name-reference
description: Claude Code's session title is the window's name; a Stop + UserPromptSubmit hook makes the tmux title follow it. Owner — referenced by /we:orchestrate, /we:story, /we:standup.
---

# The session's title is its purpose, and the tmux window follows it

A human with ten windows open re-learns what each one does by its name. Two names exist
and they used to drift: Claude Code's session title and the tmux window title. Measured
2026-09-17 in a session titled `redesign` whose tmux window still read `infra` — the user
had been keeping the two in step by hand.

**Claude's title is the source of truth.** Claude Code sets it itself when plan mode is
left, and `/rename <name>` sets it by hand. Both land in the session transcript as
`{"type":"custom-title","customTitle":"…"}`; the **last** such line is current.

## tmux follows automatically — do not rename it from a skill

`~/.claude/we/sync-tmux-title.sh`, wired as BOTH a `Stop` and a `UserPromptSubmit` hook in
`~/.claude/settings.json`, reads the last title off the end of the transcript (`tac`, ~40 ms
on a 200 MB file) and renames the pane's window when it differs. A skill that renamed tmux
itself would be overwritten at the next turn — so skills leave tmux alone.

Why two events: `/rename` is a local command, and the user typically types it together
with their next prompt. Wired on `Stop` alone the window keeps its old name for the whole
following turn (measured 2026-09-19: a `/rename WA-2302` sent with a "go" left the window
on `bash` through the entire build turn). `UserPromptSubmit` fires before that turn starts,
so the window is right while the work runs; `Stop` still covers a title Claude Code sets
itself mid-turn.

```bash
tac "$transcript" | grep -m1 '"type":"custom-title"' | jq -r .customTitle   # what the hook reads
```

## What a skill does when the window's purpose changes

`/rename` is a slash command and no tool runs it. So when a story is loaded, an epic run
boots, or a close-out ends: print the exact line **once**, and nothing else about it —

```
/rename <name>
```

— where `<name>` is short and is what the window IS: the ticket key (`WA-2284`) or one
word for the epic (`design-v2`). Never a sentence. After plan mode Claude Code has usually
already set a title; print the line only when that title is not the name you would choose.
