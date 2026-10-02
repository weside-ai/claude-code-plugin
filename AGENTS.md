# claude-code-plugin — developer guide

Repository of the Claude Code plugin `we` (Agentic Product Ownership plus build pipeline) by
[weside.ai](https://weside.ai). User-facing overview: [README.md](README.md).

This is a public repository. Never commit internal weside architecture, API keys, internal URLs,
customer data or proprietary business logic.

## Binding contract

Every file under `we/` follows [we/AUTHORING.md](we/AUTHORING.md): what earns a line, the shape of a
skill, built-ins first, the measured facts a skill must respect.

## Layout

```text
.claude-plugin/marketplace.json   publisher weside-ai
we/                               plugin root
  .claude-plugin/plugin.json      name, version, userConfig
  .mcp.json                       weside-mcp (OAuth, optional)
  AUTHORING.md                    authoring contract
  skills/<verb>/SKILL.md          one directory per /we:<verb>
  agents/                         dev-medium, dev-high, council-<role> lenses
  references/                     shared contracts (apo-hierarchy, plan-commit, worker-dispatch, ticketing, privacy-guard,
                                  optimization-store, instruction-sources, instruction-authoring)
  hooks/                          hooks.json + SessionStart materialize and optimization reminder, Stop store-conversation,
                                  PreToolUse verification gate, SubagentStart/Stop timing
  scripts/                        load-rules.py, check-instruction-budget.py, identity cache, statusline
  templates/agents-skill/         rule bridge /we:setup installs for non-Claude agents
docs/                             user docs (index: docs/README.md)
tour/index.html                   one-page tour, served at plugin.weside.ai/tour/
scripts/                          repo validators (frontmatter, structure)
```

## Conventions

- Every verb works without a weside account; Companion features are additive.
- Skills name ticketing actions generically ("move to In Review"), per `we/references/ticketing.md`.
- Tool commands are detected from the project's marker files, never hard-coded.
- No weside application paths, internal ticket keys or internal URLs in `we/`.
- A shared fact lives in one file under `we/references/`; skills point at it.

## Checks before a commit

```bash
pre-commit run --all-files
python3 scripts/validate-frontmatter.py we/skills/*/SKILL.md we/agents/*.md
bash scripts/validate-plugin-structure.sh
python3 -m pytest -q we
python3 we/scripts/check-instruction-budget.py
```

## Versioning

`/plugin update` compares `version` in `we/.claude-plugin/plugin.json`; a push to `main` without a
bump stays invisible to users. Patch for fixes and docs, minor for new or changed behaviour, major
for removed or renamed verbs. After a pushed bump: `claude plugins update we@weside-ai`.

## Plugin and weside backend

The plugin reaches the weside backend only through the `weside-mcp` server. A change to an MCP tool
signature needs both the backend implementation and the skills that call the tool updated.
