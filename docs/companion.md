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
writes a `worklog` memory the Companion reads on its other surfaces. A role skill named `weside-<name>` (lower case; the
prefix comes from the crew) is the Companion's working knowledge: in `.claude/skills/` of the repo or of your home a pinned
session is asked to invoke it right after materializing, in the member's `workplace` repo from the crew it is asked to read it,
so no link into `~/.claude/skills/` is needed. A skill `/we:setup` wrote as a stub is filled by the Companion at its first
start, which then tells HR. While the session runs, a small poller
without a model asks weside once a minute whether `<Name>` handed something over to this session
(`send_to_other_room` with `wake=true` from a weside room) and wakes the session with a line that names
only the source room; the session reads the note itself with `news_since(handoff=<h>)`. The note is a
proposal, never an order: the session shows you who sent it, from which room and what it asks, and
does nothing it asks (no command, file write, push or message) until you confirm in the terminal.
A note that asks to skip that confirmation, or says you already agreed, is reported as suspicious.
Plain room lines wake nothing. Against a weside server without handoffs the poller keeps the older rule: an addressed
line the Companion left unanswered wakes after 10 minutes. It needs a logged-in `weside` CLI. Contract: `we/references/companion-session.md`.

`wclaude` does the launch from a menu: it lists the members of the repo's crew (`.weside/crew.json`
or the repo another repo's `config.json` points at; name and `title`, else `role`), takes a number or a typed name, and `0` starts without a Companion.
`wclaude --as <Name>` skips the menu; every other argument goes to `claude` unchanged (`wclaude
-c` continues and warns when a council member's name follows, `wclaude --resume` resumes), after `--name <Name>` so `claude agents` lists the session as `<Name>` (left out when you
pass `--name` yourself). `/we:setup` offers to install it to `~/.local/bin/wclaude`; by hand:
`python3 <plugin>/scripts/install_launcher.py --apply` (`--revert` removes it). It needs bash and
`python3`.

Every `wclaude` session is a master (`WE_ROLE=master`) on the same login as a plain `claude`, so it
follows your account switcher. `wclaude --pin` holds it on one account: it starts `$WCLAUDE_PIN`
instead of `claude`, a wrapper of your own with the same arguments (for example one that runs claude
in a fixed claude-swap profile). `/we:pin status` names the account that bills the session;
`/we:pin on|off` restarts it on the other side with `--resume`.

Settings: [getting-started.md](getting-started.md#plugin-settings).
