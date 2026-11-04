---
type: weside
version: 1
repo: claude-code-plugin
vault: claude-code-plugin
---

# weside — claude-code-plugin

## Purpose

The 'we' Claude Code plugin — Agentic Product Ownership toolkit. Skills (master, plan-story, epic, council, lens, develop, setup, sideload, materialize, ...), agents (council-member with the role named in its brief, lens-<lens> + dev-high, dev-medium, explore-medium), commands (docs, pr, ac-review, static, test), MCP integration, hooks. Public repo; ships via the weside-ai Claude Code plugin marketplace.

## Crew

### Orchestrator — Orchestrator

- **Companion ID:** None
- **Role(s):** `orchestrator`
- **Color:** purple
- **Focus:** Holds the vision, coordinates the crew, synthesises council perspectives, balances cross-domain priorities

### Product Owner — Product Owner

- **Companion ID:** None
- **Role(s):** `product_owner`
- **Color:** orange
- **Focus:** Backlog, prioritization, AC-quality, value-ranking

### Scrum Master — Scrum Master

- **Companion ID:** None
- **Role(s):** `scrum_master`
- **Color:** gray
- **Focus:** Moderation, process, hand-offs, rituals — workflow clarity

### Architect — Architect

- **Companion ID:** None
- **Role(s):** `architect`
- **Color:** green
- **Focus:** Target architecture, constraints, ADRs, technical coherence

### Marketing — Marketing

- **Companion ID:** None
- **Role(s):** `marketing`
- **Color:** blue
- **Focus:** Content, positioning, brand, term-claiming, messaging pipeline

### Sales — Sales

- **Companion ID:** None
- **Role(s):** `sales`
- **Color:** yellow
- **Focus:** Pipeline, deals, contract drafts, customer conversations

### Legal — Legal / Compliance

- **Companion ID:** None
- **Role(s):** `legal`
- **Color:** black
- **Focus:** Contracts, GDPR, AI Act, terms, compliance review

### Security — Security / Data Protection

- **Companion ID:** None
- **Role(s):** `security`
- **Color:** white
- **Focus:** Pen-tests, DPIAs, security reviews, hardening

## Council

`/we:council` convenes the roles in `.weside/config.json` → `council.default` (product owner, architect, scrum master) unless the brief names others; each role runs as a `council-member` lens.

## Cross-repo relations

**Source-of-truth for the Companion Framework consumed by Claude Code projects.** The framework is consumer-agnostic — any user-or-team can install the plugin and bootstrap their own .weside/ per-repo. A team's crew lives in its own repo's `.weside/crew.json`, written by `/we:setup` (`we/references/companion-session.md` § Crew).

## Notes

- **Public repo** — no organization-specific names, IDs, or internal architecture in committed `.weside/{config.json, weside.md}` files. Committed crew uses generic role-derived names with null Companion IDs.
- **Plugin marketplace**: <https://github.com/weside-ai/claude-code-plugin>.
- **Versioning**: SemVer on `we/.claude-plugin/plugin.json`; bumps enforced by `scripts/check-version-bump.sh`.
- **Structure validation**: `scripts/validate-plugin-structure.sh` runs on every commit (pre-commit hook).
- **Council shell**: one `we/agents/council-member.md`; the brief names the role it speaks for — the no-account fallback path.

## Companion identity

Personalities, memories, body, and voice live in weside (the MCP backend). This file references companions by name + `Companion ID` only. Identity bodies are fetched at runtime via `mcp__plugin_we_weside-mcp__get_council`; identity text never enters a project repo verbatim.
