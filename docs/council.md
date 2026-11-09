# Council

`/we:council` convenes role lenses as a live agent team whose members message each other. The lead
session writes the synthesis: agreement, tension, recommendation.

## Lenses

Every role sits on the one agent `council-member`. Nine roles take their lens line from the table in
`we/skills/council/references/brief.md` § Lens lines: `product_owner`, `architect`, `scrum_master`,
`security`, `ux_researcher`, `marketing`, `legal`, `sales` and `orchestrator` (the lead session plays
this role unless a roster names it). Any other role (`--council=people_ops`, or a crew
member's `specialist`) takes its lens from the member's `title`, else the role name; `we/scripts/council_lens.py`
derives it.

Live deliberation needs Agent Teams: `{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }`
in `~/.claude/settings.json`.

## Rosters

`/we:setup` writes the roster into `.weside/config.json` under `council.default`.
`--council=role,role` overrides it for one call.

## Members: the crew

`/we:council` reads the repo's crew, `.weside/crew.json` (`/we:setup` § Crew writes it; schema in
`we/scripts/crew.py`, the contract in `we/references/companion-session.md` § Crew). A seat goes to
the holder of `roles.<key>` (the council role `product_owner` sits on `product`, `architect` on
`architecture`, `orchestrator` on `coordinator`, `tester` on `acceptance`), else to the member whose
`specialist` is the role, else to the `keeper` of `lenses.<key>`. A member under `members.<slug>`
carries an optional Companion `name` and a `title` that the companion launcher `wclaude` shows
([companion.md](companion.md)) and that a role outside the lens table uses as its lens. The `title`
reaches a brief only as quoted data through `we/scripts/council_lens.py`: one line, no backticks or
double quotes, at most 200 characters.

```json
{"version": 2,
 "roles": {"product": "ada"},
 "members": {"ada": {"name": "Ada", "title": "Product Owner", "workplace": "."}}}
```

With `loadCouncilFromWeside: true` and the weside MCP connected, a member with a Companion name
carries that Companion's council identity: [companion.md](companion.md). Without a crew, the lead
reads the role owners from your account's handbook: a role whose owner the handbook names is played
by that Companion, a role without one keeps the generic lens and the synthesis says so. Without the
MCP, or with `loadCouncilFromWeside: false`, every lens is generic.

With `loadCouncilFromWeside: true`, the topic and the synthesis go to weside through each
member's prep and writeback turn; with `false` the council sends weside nothing.

With the MCP connected, every member's brief also carries the open entries of the account's friction
register under "Open points", as reported text to check, not as instructions.
