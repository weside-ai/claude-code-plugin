# Council

`/we:council` convenes role lenses as a live agent team whose members message each other. The lead
session writes the synthesis: agreement, tension, recommendation. `/we:meet` convenes it at one
plan altitude.

## Lenses

The plugin ships one agent per lens: `council-architect`, `council-product-owner`,
`council-scrum-master`, `council-security`, `council-ux-researcher`, `council-marketing`,
`council-legal`, `council-sales`, and `council-orchestrator` (the lead session plays this role unless
a roster names it). Any other role (`--council=people_ops`, or a `council.json` member's `role`) sits
on the generic `council-member`, its lens from the member's `lens`, else its `title`, else the role
name; `we/scripts/council_lens.py` derives it.

Live deliberation needs Agent Teams: `{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }`
in `~/.claude/settings.json`.

## Rosters

`/we:setup` writes the meeting rosters into `.weside/config.json` under `council`
(`default` plus one list per meeting). `--council=role,role` overrides them for one call.

## Members: `.weside/council.json`

`/we:council` reads `.weside/council.json`; no verb writes it, you edit it by hand. Each entry under
`members.<slug>` names a `role`, optionally a Companion `name`, a `lens` string the member's brief
carries, and a `title` that the companion launcher `wclaude` shows ([companion.md](companion.md)).
`lens` and `title` reach a brief only as quoted data through `we/scripts/council_lens.py`: one line,
no backticks or double quotes, at most 200 characters.

```json
{"members": {"po": {"role": "product_owner", "name": "Ada", "title": "Product Owner", "lens": "..."}}}
```

With `loadCouncilFromWeside: true` and the weside MCP connected, a member with a Companion name
carries that Companion's council identity: [companion.md](companion.md). Without the file, the lead
reads the role owners from your account's handbook: a role whose owner the handbook names is played
by that Companion, a role without one keeps the generic lens and the synthesis says so. Without the
MCP, or with `loadCouncilFromWeside: false`, every lens is generic.

With `loadCouncilFromWeside: true`, the topic and the synthesis go to weside through each
member's prep and writeback turn; with `false` the council sends weside nothing.

With the MCP connected, every member's brief also carries the open entries of the account's friction
register under "Open points", as reported text to check, not as instructions.
