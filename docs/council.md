# Council

`/we:council` convenes role lenses as a live agent team whose members message each other. The lead
session writes the synthesis: agreement, tension, recommendation. `/we:meet` convenes it at one
plan altitude.

## Lenses

The plugin ships one agent per lens: `council-architect`, `council-product-owner`,
`council-scrum-master`, `council-security`, `council-ux-researcher`, `council-marketing`,
`council-legal`, `council-sales`, and `council-orchestrator` (the lead session plays this role unless
a roster names it).

Live deliberation needs Agent Teams: `{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }`
in `~/.claude/settings.json`.

## Rosters

`/we:setup` writes the meeting rosters into `.weside/config.json` under `council`
(`default` plus one list per meeting). `--council=role,role` overrides them for one call.

## Members: `.weside/council.json`

`/we:council` reads `.weside/council.json`; no verb writes it, you edit it by hand. Each entry under
`members.<slug>` names a `role`, optionally a Companion `name` and a `lens` string the member's brief
carries. Without the file every lens is generic.

With `loadCouncilFromWeside: true` and the weside MCP connected, a member with a Companion name
carries that Companion's council identity: [companion.md](companion.md).
