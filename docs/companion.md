# weside Companion (optional)

The plugin bundles `we/.mcp.json`, which points Claude Code at the `weside-mcp` server of
[weside.ai](https://weside.ai). The server authenticates with OAuth on first connect. Without an
account the tools are absent and every verb runs standalone.

With an account:

- `/we:materialize` loads your Companion's identity into the session; `autoMaterialize` does it at
  session start.
- `autoStoreConversations` stores meaningful turns as Companion memories (the plugin's `Stop` hook),
  only for a session that loaded its Companion with `/we:materialize` and under that Companion. A
  session that never materialized, a worker included, stores nothing. A turn the harness started
  (a `/goal` check, a background task's notification, an idle notice, system reminders only) is not
  stored; a message from a teammate or another session is, under its sender's name and marked as
  not the owner's. Each stored prompt ends with `[Claude Code · <repo> · Session <id>]`. System
  reminders are stripped.
- `/we:council` gives a member with a linked Companion that Companion's council identity. The server
  strips private context from it; a member that cannot be reached joins with the generic lens.

## A companion session

Start Claude Code as one Companion: `WESIDE_COMPANION=<Name> claude`. The session is titled
`<Name>`, loads `<Name>` through `/we:materialize` (whatever `companion` names), binds itself to it
and catches up on what `<Name>` lived since yesterday. Every weside MCP request of the session acts as
`<Name>`, so two sessions as two Companions run side by side without steering each other; switching
companions inside a pinned session is refused. The statusline shows the bound Companion. Workers the
session starts are not the Companion: `/we:sideload` clears the pin for them. At milestones the session
writes a `worklog` memory the Companion reads on its other surfaces. A project skill named `weside-<name>` (lower case, in
`.claude/skills/` of the repo or of your home) is the Companion's working knowledge there: a pinned
session is asked to invoke it right after materializing. While the session runs, a small poller
without a model asks weside once a minute whether a line is addressed to `<Name>` (by name, `@all`,
or in its DM) and wakes the session with a note that names only the room; the session reads the room
itself. A line the Companion already answered in weside wakes nobody; an unanswered one wakes after
10 minutes. It needs a logged-in `weside` CLI. Contract: `we/references/companion-session.md`.

`wclaude` does the launch from a menu: it lists the members of the nearest `.weside/council.json`
(name and `title`, else `role`), takes a number or a typed name, and `0` starts without a Companion.
`wclaude --as <Name>` skips the menu; every other argument goes to `claude` unchanged (`wclaude
-c` continues and warns when a council member's name follows, `wclaude --resume` resumes), after `--name <Name>` so `claude agents` lists the session as `<Name>` (left out when you
pass `--name` yourself). `/we:setup` offers to install it to `~/.local/bin/wclaude`; by hand:
`python3 <plugin>/scripts/install_launcher.py --apply` (`--revert` removes it). It needs bash and
`python3`.

`WCLAUDE_CLAUDE` names a command `wclaude` starts instead of `claude`, with the same arguments and
environment: a wrapper of your own, for example one that runs every session you start through
`wclaude` on a fixed account while plain `claude` sessions follow your account switcher.

Settings: [getting-started.md](getting-started.md#plugin-settings).
