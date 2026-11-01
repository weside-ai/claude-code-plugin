---
name: pin
description: "Account pin of a master session: status, on, off. Trigger: \"/we:pin\"."
---

# /we:pin — account pin of a master session

1. Run `bash ${CLAUDE_PLUGIN_ROOT}/scripts/pin.sh <status|on|off>` (no argument = `status`) and relay
   its one line. Never read or print a credential; the script reads only the account's e-mail.
2. `on`/`off` schedule a successor (`--resume` of this session id, same companion, `WE_ROLE=master`)
   that waits until this session ends. Tell the user to `/exit` now; save nothing in between.
3. Outside tmux the script prints the command instead: relay it verbatim, the user runs it after `/exit`.

Pinned means the session was started through `$WCLAUDE_PIN` (`wclaude --pin`) and runs in its own
config profile (`CLAUDE_CONFIG_DIR`); unpinned means the global login, like a plain `claude`. A live
session cannot change sides: the profile's credential belongs to the account switcher, so a link to
the global login would let the switcher write through it. Contract:
`${CLAUDE_PLUGIN_ROOT}/references/companion-session.md` § Launch and pin.
