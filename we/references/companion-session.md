# Companion session

A Claude Code session that acts as a weside Companion. One promise across four paths: the MCP
header, the session title, the Stop hook and the statusline name the same companion, and a worker
gets none of them. Skills that start, bind or spawn sessions point here.

## Launch and pin

`WESIDE_COMPANION=<Name> claude` pins the session. The plugin's `.mcp.json` sends
`X-Weside-Companion: ${WESIDE_COMPANION:-}` on every weside MCP request, so every tool acts as
`<Name>` whatever another session selected; an empty value is no pin. A pinned request never
changes the account's selection: `select_companion` to another name is refused, so talking as a
second companion takes a second session. An unknown name answers HTTP 422.

`scripts/wclaude` is the launcher: a menu over the members of the nearest `.weside/council.json`
(optional `title` per member, the council ignores it), `-c <Name>` without a menu, `0` clears the
pin; every other argument goes to `claude`. It passes `--name <Name>` unless you pass a name: the
hook's `sessionTitle` does not rename a new session's row in `claude agents` (Claude Code 2.1.310). `/we:setup` § 5 installs it through
`scripts/install_launcher.py`.

A companion session is a normal Claude Code session; what binds it to its companion is the pin
header, so start companion sessions through `wclaude` (a plain `claude` is unpinned and acts as the
account's selected companion).

## Name and binding

- The SessionStart hook (`hooks/materialize_on_start.py`) titles a pinned session `<Name>` and asks
  it to run `/we:materialize`. It skips a session started with `--agent`.
- `/we:materialize` binds the session (its step 5 owns the call). The script's docstring owns the
  binding file (one per session id, mode 600, 30-day prune) and
  refuses a name other than the pin.
- The binding is the one record the Stop hook and the statusline read. `/clear` starts a new session
  id, so the session is unbound until it materializes again; with a pin the hook asks for that.
- A bound session keeps its companion's name as its title. Every skill that would print
  `/rename <KEY>` skips it when
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/identity_cache.py binding --session "$CLAUDE_CODE_SESSION_ID"`
  exits 0 (the run key reaches the statusline through `~/.claude/we-focus/`).

## Workers

A worker is steered by the companion session and is never the companion. A `claude --bg` worker
starts with the pin cleared: `WESIDE_COMPANION= claude --bg "<task>"`, so it is not titled, not
asked to materialize, not bound, and stores no turn. `Agent` subagents share the session's MCP
connection and fire no SessionStart. A teammate in its own process inherits the environment: it gets
the title and the note, and the note tells a spawned session to ignore it.

## Writeback

`autoStoreConversations` stores the bound session's turns as conversation memories. Deliberate
writeback happens at the milestones (a decision, a plan approved, a PR opened or merged, a
blocker):

```text
save_memory(memory_type="worklog",
            title="<repo> · <key or topic> · <what>",
            content="<what was decided, what was done, refs: PR, commit, plan path>",
            repo_id="<repo_id>")
```

`repo_id` is derived as `_derive_repo_id` in `hooks/store_conversation_hook.py` does. The companion
reads the entry on its other surfaces through its timeline and memory tools. A decision the crew
must know also goes to the shared room through `execute_tool(name="send_to_other_room", …)`.
`execute_tool` takes its `arguments` as a JSON string.

## Catch-up

`/we:materialize` ends with one `read_timeline` call (its step 6 owns the call and the error
handling), so the session starts from what the companion lived elsewhere.

## Role owners

Who owns a role (CI, infrastructure, legal …) is read from the account's handbook (the `handbook/`
notes of the vault) at the moment it is needed, never from memory or a list in a repo. A
materialized companion carries the handbook in its identity; otherwise
`execute_tool(name="notes_search", arguments='{"query": "<role name>"}')` and `notes_get` on the
hits under `handbook/`.
