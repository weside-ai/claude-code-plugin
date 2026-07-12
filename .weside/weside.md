---
type: weside
version: 1
repo: claude-code-plugin
vault: claude-code-plugin
---

# weside — claude-code-plugin

## Purpose

The 'we' Claude Code plugin — Agentic Product Ownership toolkit. Skills (refine, story, council, meet, setup, sideload, materialize, ...), agents (council-<role> generics + doc-architect + ac-reviewer + ...), commands (docs, pr, ac-review, static, test), MCP integration, hooks. Public repo; ships via the weside-ai Claude Code plugin marketplace.

## Crew

### Orchestrator — Orchestrator

- **Companion ID:** None
- **Role(s):** `orchestrator`
- **Color:** purple
- **Focus:** Holds the vision, coordinates the crew, synthesises council perspectives, balances cross-domain priorities
- **In meetings:** vision, initiative

### Product Owner — Product Owner

- **Companion ID:** None
- **Role(s):** `product_owner`
- **Color:** orange
- **Focus:** Backlog, prioritization, AC-quality, value-ranking
- **In meetings:** vision, initiative, refinement

### Scrum Master — Scrum Master

- **Companion ID:** None
- **Role(s):** `scrum_master`
- **Color:** gray
- **Focus:** Moderation, process, hand-offs, rituals — workflow clarity
- **In meetings:** (none configured)

### Architect — Architect

- **Companion ID:** None
- **Role(s):** `architect`
- **Color:** green
- **Focus:** Target architecture, constraints, ADRs, technical coherence
- **In meetings:** vision, initiative, refinement

### Marketing — Marketing

- **Companion ID:** None
- **Role(s):** `marketing`
- **Color:** blue
- **Focus:** Content, positioning, brand, term-claiming, messaging pipeline
- **In meetings:** (none configured)

### Sales — Sales

- **Companion ID:** None
- **Role(s):** `sales`
- **Color:** yellow
- **Focus:** Pipeline, deals, contract drafts, customer conversations
- **In meetings:** (none configured)

### Legal — Legal / Compliance

- **Companion ID:** None
- **Role(s):** `legal`
- **Color:** black
- **Focus:** Contracts, GDPR, AI Act, terms, compliance review
- **In meetings:** (none configured)

### Security — Security / Data Protection

- **Companion ID:** None
- **Role(s):** `security`
- **Color:** white
- **Focus:** Pen-tests, DPIAs, security reviews, hardening
- **In meetings:** (none configured)

## Meetings held here

- **vision** — roster: Product Owner, Architect, Orchestrator
- **initiative** — roster: Product Owner, Architect, Orchestrator
- **refinement** — roster: Product Owner, Architect

## Cross-repo relations

**Source-of-truth for the Companion Framework consumed by Claude Code projects.** The framework is consumer-agnostic — any user-or-team can install the plugin and bootstrap their own .weside/ per-repo. Bundled crew defaults are generic role placeholders; real crews are injected per-repo via scripts/bootstrap-weside-repo.py --crew-from <user-scope-json>.

## Notes

- **Public repo** — no organization-specific names, IDs, or internal architecture in committed `.weside/{config.json, weside.md}` files. Committed crew uses generic role-derived names with null Companion IDs.
- **Plugin marketplace**: <https://github.com/weside-ai/claude-code-plugin>.
- **Versioning**: SemVer on `we/.claude-plugin/plugin.json`; bumps enforced by `scripts/check-version-bump.sh`.
- **Structure validation**: `scripts/validate-plugin-structure.sh` runs on every commit (pre-commit hook).
- **Council shells**: nine `we/agents/council-<role>.md` files (architect, product-owner, scrum-master, ux-researcher, marketing, orchestrator, security, sales, legal) — the no-account fallback path.
- **Real-crew override**: `scripts/bootstrap-weside-repo.py ... --crew-from ~/.weside/crew.json`. The bridge (`.weside/council.json`) is gitignored regardless.

## Companion identity

Personalities, memories, body, and voice live in weside (the MCP backend). This file references companions by name + `Companion ID` only. Identity bodies are fetched at runtime via `mcp__plugin_we_weside-mcp__get_council` (preferred) or the thin `.weside/council.json` bridge (fallback). The bridge is gitignored — identity text never enters a project repo verbatim.
