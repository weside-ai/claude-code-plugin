# weside Companion (optional)

The plugin bundles `we/.mcp.json`, which points Claude Code at the `weside-mcp` server of
[weside.ai](https://weside.ai). The server authenticates with OAuth on first connect. Without an
account the tools are absent and every verb runs standalone.

With an account:

- `/we:materialize` loads your Companion's identity into the session; `autoMaterialize` does it at
  session start.
- `autoStoreConversations` stores meaningful turns as Companion memories (the plugin's `Stop` hook).
- `/we:council` gives a member with a linked Companion that Companion's council identity. The server
  strips private context from it; a member that cannot be reached joins with the generic lens.

Settings: [getting-started.md](getting-started.md#plugin-settings).
