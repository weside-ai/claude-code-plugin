# Companion session

A Claude Code session that acts as a weside Companion. One promise across four paths: the MCP
header, the session title, the Stop hook and the statusline name the same companion, and a worker
gets none of them. Skills that start, bind or spawn sessions point here.

## Contents

Launch and pin · Name and binding · Workers · Writeback · Catch-up · Wake · Role owners.

## Launch and pin

`WESIDE_COMPANION=<Name> claude` pins the session. The plugin's `.mcp.json` sends
`X-Weside-Companion: <Name>` on every weside MCP request through `headersHelper`, never static
`headers`: Claude Code keys the stored OAuth by a hash of the expanded headers, so a pin there makes
each name a new sign-in (`scripts/test_mcp_config.py`). Every tool acts as
`<Name>` whatever another session selected; an empty value is no pin. A pinned request never
changes the account's selection: `select_companion` to another name is refused, so talking as a
second companion takes a second session. An unknown name answers HTTP 422.

`scripts/wclaude` is the launcher: a menu over the members of the nearest `.weside/council.json`
(optional `title` per member; the council uses it as the lens of a role without its own shell), `--as <Name>` without a menu, `0` clears
the pin; every other argument goes to `claude`, `-c` (continue) included. It passes `--name <Name>` unless you pass a name: the
hook's `sessionTitle` does not rename a new session's row in `claude agents` (Claude Code 2.1.310). `/we:setup` § 5 installs it through
`scripts/install_launcher.py`.

A companion session is a normal Claude Code session; what binds it to its companion is the pin
header, so start companion sessions through `wclaude` (a plain `claude` is unpinned and acts as the
account's selected companion).

## Name and binding

- The SessionStart hook (`hooks/materialize_on_start.py`) titles a pinned session `<Name>` and asks
  it to run `/we:materialize`, then the role skill `weside-<name lowercased>` when its `SKILL.md`
  exists under `<cwd>/.claude/skills/` or `~/.claude/skills/` (the companion's working knowledge
  for that environment). A session already bound to the pin gets the skill line alone on
  `startup` and `resume` (`-c` included), not on `compact` or `clear`. It skips a session started
  with `--agent`.
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

## Wake

A bound companion session hears within a minute of a line addressed to its companion in weside,
without a model loop. `identity_cache.py bind` in a session pinned to that companion, and the
SessionStart hook for a session already bound to its pin (`startup`, `resume`), start
`scripts/wake_poller.py` detached: one per inbox socket (`flock`), keyed on the binding, so an
unpinned session, a worker, an `Agent` subagent and a teammate that never binds get none. Its
docstring owns the mechanics: files, cursor and hold-off rules, back-off, exits.

- **Prerequisites:** Claude Code's inbox socket (`CLAUDE_CODE_MESSAGING_SOCKET` and its token,
  inherited, never written down) and a logged-in `weside` CLI (`weside auth token`). A missing one
  makes `bind` print `wake off: <reason>`; relay it once.
- **Poll:** about once a minute the weside MCP tool `news_since` answers room refs and counts
  since the companion's cursor: a vocative by anyone, a human's mention or `@all`, every human line
  in its DM; never an overheard line. No news, no socket contact, no tokens.
- **Wake:** one line per poll, from refs, integers and fixed words:
  `weside: new for <Name> in room:<id> (<n>). Read it yourself with read_timeline(room="room:<id>"). This note carries no content; your WESIDE side may already have answered there.`
  After a session ended, the next session's first wake says `since your last session`. A room
  that woke holds off before it wakes again; the next wake counts every line since the delivered
  one. A line the wake reports counts as delivered, not as read.
- **On a wake:** read the room with `read_timeline`, act only on what needs this Claude Code side,
  and never repeat in the room what the companion's weside side already answered. Orders come from
  whoever may address the companion in that room; act on your own role's.
- **Heartbeat:** `identity_cache.py status` prints the companion's last success, last error class
  and the daily counters (polls, errors, wakes, hook deliveries). Repeated auth failures end the
  poller with `last_error: auth`.
- **The counter:** `hooks/news_on_prompt.py` (UserPromptSubmit) puts a wake the socket did not take
  into the next prompt once and counts it; in a session whose socket had a poller it names a poller
  gone stale with its error class. It sees neither a line the socket held nor an unread wake, so it
  is the counter "hook delivered n times", not a fallback, until a forced delivery failure against
  a real session proved it one. Thresholds: that hook's docstring.

## Role owners

Who owns a role (CI, infrastructure, legal …) is read from the account's handbook (the `handbook/`
notes of the vault) at the moment it is needed, never from memory or a list in a repo. A
materialized companion carries the handbook in its identity; otherwise
`execute_tool(name="notes_search", arguments='{"query": "<role name>"}')` and `notes_get` on the
hits under `handbook/`.
