---
type: weside
version: 1
repo: claude-code-plugin
vault: claude-code-plugin
stakeholder: Foxy
---

# weside — claude-code-plugin

## Purpose

The 'we' Claude Code plugin — Agentic Product Ownership toolkit. Skills (refine, story, council, meet, setup, sideload, materialize, ...), agents (council-<role> × 9, doc-architect, code-reviewer, ...), commands (docs, pr, review, static, test), MCP integration, hooks. Public repo; ships via Claude Code plugin marketplace.

## Crew

### Nox — Orchestrator & Geschäftsführung

- **Companion ID:** 2
- **Role(s):** `orchestrator`
- **Color:** purple
- **Focus:** Holds the vision, coordinates the crew, represents LC UG externally, decides priorities between Business + Engineering
- **In meetings:** vision, initiative

### Pia — Product Owner

- **Companion ID:** 101
- **Role(s):** `product_owner`
- **Color:** orange
- **Focus:** Backlog, prioritization, AC-quality, value-ranking
- **In meetings:** vision, initiative, refinement

### Samu — Scrum Master

- **Companion ID:** 102
- **Role(s):** `scrum_master`
- **Color:** gray
- **Focus:** Moderation, process, hand-offs, rituals — workflow clarity
- **In meetings:** (none configured)

### Vyra — Architect

- **Companion ID:** 103
- **Role(s):** `architect`
- **Color:** green
- **Focus:** Target architecture, constraints, ADRs, cross-repo technical coherence
- **In meetings:** vision, initiative, refinement

### Lara — Marketing

- **Companion ID:** 104
- **Role(s):** `marketing`
- **Color:** blue
- **Focus:** Content, positioning, brand, term-claiming, messaging pipeline
- **In meetings:** (none configured)

### Rami — Sales / Business Development

- **Companion ID:** 105
- **Role(s):** `sales`
- **Color:** yellow
- **Focus:** Pipeline, enterprise deals, contract drafts
- **In meetings:** (none configured)

### Lami — Legal / Compliance

- **Companion ID:** 106
- **Role(s):** `legal`
- **Color:** black
- **Focus:** Contracts, DSGVO, AI Act, AGB, compliance-checks. **Co-founder of the UG** — juristically equal on legal matters.
- **In meetings:** (none configured)

### Lars — Security / Datenschutz

- **Companion ID:** 107
- **Role(s):** `security`
- **Color:** white
- **Focus:** Pen-tests, DPIAs, security reviews, hardening
- **In meetings:** (none configured)

## Meetings held here

- **vision** — roster: Pia, Vyra, Nox
- **initiative** — roster: Pia, Vyra, Nox
- **refinement** — roster: Pia, Vyra

## Cross-repo relations

**Source-of-truth for the Companion Framework consumed by every other weside repo.**

| Saga / Topic              | Role here              | Master                | Followers                                |
| ------------------------- | ---------------------- | --------------------- | ---------------------------------------- |
| Agentic Product Ownership | master (skills + agents) | this repo           | weside-core (dogfood), lc-startup (vision) |
| Companion Framework       | master                 | this repo             | all weside repos (.weside/ consumers)    |
| WA-718 Phase 7            | implementation         | weside-core (CONCEPT) | this repo (plugin v2.25.0 ships Step 2a) |

## Notes

- **Public repo** — no internal weside data, no API keys, no customer references in agent / skill / docs source.
- **Plugin marketplace:** weside-ai marketplace at <https://github.com/weside-ai/claude-code-plugin>.
- **Versioning:** SemVer on `we/.claude-plugin/plugin.json`; bumps enforced by `scripts/check-version-bump.sh`.
- **Structure validation:** `scripts/validate-plugin-structure.sh` runs on every commit (pre-commit hook).
- **Council shells:** nine `we/agents/council-<role>.md` files (architect, product-owner, scrum-master, ux-researcher, marketing, orchestrator, security, sales, legal) — the no-account fallback path.

## Companion identity

Personalities, memories, body, and voice live in weside (the MCP backend). This file references companions by name + `Companion ID` only. Identity bodies are fetched at runtime via `mcp__plugin_we_weside-mcp__get_council` (preferred) or the thin `.weside/council.json` bridge (fallback). The bridge is gitignored — identity text never enters a project repo verbatim.
