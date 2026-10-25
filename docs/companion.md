# weside Companion (optional)

The plugin bundles `we/.mcp.json`, which points Claude Code at the `weside-mcp` server of
[weside.ai](https://weside.ai). The server authenticates with OAuth on first connect. Without an
account the tools are absent and every verb runs standalone.

With an account:

- `/we:materialize` loads your Companion's identity into the session; `autoMaterialize` does it at
  session start.
- `autoStoreConversations` stores meaningful turns as Companion memories (the plugin's `Stop` hook),
  only for a session that loaded its Companion with `/we:materialize` and under that Companion. A
  session that never materialized, a worker included, stores nothing.
- `/we:council` gives a member with a linked Companion that Companion's council identity. The server
  strips private context from it; a member that cannot be reached joins with the generic lens.

## A companion session

Start Claude Code as one Companion: `WESIDE_COMPANION=<Name> claude`. The session is titled
`<Name>`, loads `<Name>` through `/we:materialize` (whatever `companion` names), binds itself to it
and catches up on what `<Name>` lived since yesterday. Every weside MCP request of the session acts as
`<Name>`, so two sessions as two Companions run side by side without steering each other; switching
companions inside a pinned session is refused. The statusline shows the bound Companion. Workers the
session starts are not the Companion: `/we:sideload` clears the pin for them. At milestones the session
writes a `worklog` memory the Companion reads on its other surfaces. Contract:
`we/references/companion-session.md`.

Settings: [getting-started.md](getting-started.md#plugin-settings).
