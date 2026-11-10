---
name: start
description: "Start check of the crew's main companion: human, companion, role and pin against crew.json, then the crew restore after a crash and the board. Triggers: \"/we:start\"; `wclaude --start` opens the session with it."
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
3. Board: a session started by `wclaude --start` opened `/board` itself (`WE_START=1`, checked
   against `roles.coordinator`). Started otherwise, tell the user to type `/board`: a skill cannot
   run a pane command.

Done when:
- [ ] the four check lines are relayed, every FAIL with its fix
- [ ] the restore was offered after a resume or crash, or the missing `launch.restore` named
- [ ] the board is open or the user was told to type `/board`
