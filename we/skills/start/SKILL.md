---
name: start
description: "Start check of the crew's main companion: human, companion, role and pin against crew.json, then the crew restore after a crash, the offer to start the rest of the crew and the board. Triggers: \"/we:start\"; `wclaude --start` opens the session with it."
---

# /we:start — the main companion's start

The session half of the main companion's start; the shell half is `wclaude --start`, and the whole
flow is owned by `${CLAUDE_PLUGIN_ROOT}/references/companion-session.md` § Launch and pin.

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/start.py check` and relay its four lines.
   - A `FAIL human`, `FAIL companion` or `FAIL WE_ROLE` means a wrong start: tell the user to `/exit` and run
     `wclaude --start` from a shell; do nothing else in this session.
   - A `FAIL pin` names the fix (`/we:pin on|off`); offer it, never run it unasked.
2. Restore, only when this session resumed (its transcript holds turns before this one) or the user
   names a crash: run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/start.py restore`.
   - Exit 1: the crew sets no `launch.restore`; say so in one line and go on.
   - Otherwise run the printed command as is: it prints a plan and starts nothing. Relay the counts
     and every `PIN`, `WARN` and `FAIL` line, then ask once whether to run it with `--apply`.
   - On a yes, run `<command> --apply` in the background (it paces its starts over minutes) and
     report its last line when it ends. On a no, leave it.
3. The rest of the crew, in the coordinator's session only (`WE_ROLE_ID=coordinator`): run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/start.py roster` and relay its
   lines (each companion with its roles, its human, and whether it runs, starts here, or runs on
   another human's machine). Then ask once: "Start the ones marked `start:` too? Default: no."
   - Only an explicit yes starts them: each `start:` command in its own tmux window
     (`tmux new-window -d -n <name> <command>`), never one marked `runs`; no answer, no start.
4. Board: a session started by `wclaude --start` opened `/board` itself (`WE_START=1`, checked
   against `roles.coordinator`). Started otherwise, tell the user to type `/board`: a skill cannot
   run a pane command.

Done when:
- [ ] the four check lines are relayed, every FAIL with its fix
- [ ] the restore was offered after a resume or crash, or the missing `launch.restore` named
- [ ] the roster is relayed and the start of the rest asked once, default no, nothing started without a yes
- [ ] the board is open or the user was told to type `/board`
