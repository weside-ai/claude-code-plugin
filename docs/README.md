# Documentation

- [Getting started](getting-started.md) — install, `/we:setup`, the first story from plan to PR.
- [Workflow](workflow.md) — epics and stories, the build pipeline, the crew, the effort rule.
- [The flow pane](flow.md) — `/flow`: traffic lights per pipeline step, buttons, data sources.
- [The board pane](../we/docs/board.md) — `/board`: the workspace board the crew's coordinator keeps, its file schema, live and start-mode lamps.
- [Council](council.md) — role lenses, the roster, the members from the repo's crew (`.weside/crew.json`).
- [weside Companion](companion.md) — the optional MCP connection and its settings.
- [tmux attention](tmux.md) — the window title turns white while a session waits for you.

## Options

Set in `/plugin` → we → Configure (or `/plugin settings we@weside-ai`). The companion options need a
weside.ai account.

| Option | Effect | Default | Details |
|---|---|---|---|
| `companion` | weside Companion name | empty | [companion.md](companion.md) |
| `autoMaterialize` | loads the Companion at session start | `false` | [companion.md](companion.md) |
| `autoStoreConversations` | stores meaningful turns as Companion memories, only in a session that ran `/we:materialize` | `false` | [companion.md](companion.md) |
| `loadCouncilFromWeside` | council members carry linked Companions' identities; `false` keeps every lens generic | `true` | [council.md](council.md) |
| `boardFile` | the board file `/board` reads in a repo without a crew file; with one, the crew's `board.file`, else `board.json` in its state folder (`WE_STATE_DIR`, the crew's `state_dir`, `~/.claude/we-state`) wins. Its answers file `<stem>-answers.jsonl` and delivery ledger `<stem>-deliveries.jsonl` sit beside it | `~/.claude/we-state/board.json` | [board.md](../we/docs/board.md#the-file) |
| `boardAutoOpen` | opens `/board` at session start: `off`, `on` (every session), `orchestrator` (only the session of the crew's coordinator, `roles.coordinator`) | `off` | [board.md](../we/docs/board.md#opening-it) |
| `masterProfile` | the claude-swap profile master sessions run in; turns on `/board`'s red start-mode rules | empty | [board.md](../we/docs/board.md#the-live-column) |
| `tmuxAttention` | inside tmux, the window title turns white while the session waits for you, grey once it rests | `true` | [tmux.md](tmux.md) |
| `tmuxAttentionStyle` | the tmux style of a waiting window | `bg=white,fg=black` | [tmux.md](tmux.md) |
| `tmuxIdleStyle` | the tmux style of a resting window | `bg=colour240,fg=white` | [tmux.md](tmux.md) |

The verb list lives in the [README](../README.md#verbs). The authoring contract for everything in
`we/` is [we/AUTHORING.md](../we/AUTHORING.md).
