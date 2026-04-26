---
name: doc-improve-docs-reference
description: Type-specific addendum for reviewing files under docs/ — TurboVault frontmatter (type/domain/status), placement fit, format adherence (architecture/journey/primitive-detail), cross-reference coherence, duplicate-content policy. Loaded on demand by the doc-improve skill.
---

# Reference: Reviewing `docs/` files

This is the type-specific addendum for files under `docs/`. Apply **after**
the four universal pillars from `SKILL.md`. Unique concerns: TurboVault
indexability via frontmatter, fit with the documented placement of the file
type, and adherence to the format templates from `doc-standards.md`.

---

## Source of Truth

Read `.claude/rules/quality/doc-standards.md` once at boot — it defines:

- The 4-layer knowledge system and `docs/` tree.
- The architecture / journey / primitive-detail format templates.
- The frontmatter schema (`type`, `domain`, `status` required).
- The placement decision tree.
- The promotion criteria (foundation, primitive).
- Size guidelines per doc-type.

Cite that rule by section when proposing fixes. Don't restate it here.

---

## Pillar 5a — TurboVault Frontmatter

### Required fields

Every `docs/**/*.md` MUST carry:

```yaml
---
type: architecture | primitive | adr | foundation | guide | plan | vision | security | journey
domain: [voice, billing, companion, memory, auth, tools, channels, proactivity, observability, data-model, deployment, platform]
status: current | draft | outdated | superseded
                                              # ADRs: accepted | superseded | deprecated
---
```

Optional fields: `superseded-by` (ADRs), `story` (plans), `created`, `updated`.

### Why it matters

TurboVault MCP indexes the frontmatter. Without it, `search_by_frontmatter`
and `advanced_search` can't filter by type or domain — meaning the doc is
findable only by full-text grep, not by structured query.

### Method

```bash
head -10 <doc>                                  # eyeball
mcp__turbovault__inspect_frontmatter            # if MCP available
```

### Findings to look for

- **Missing frontmatter entirely** — **BLOCKER for findability.**
- **Wrong `type:`** — e.g. `type: architecture` on a file that's actually a
  guide. Misclassifies in TurboVault.
- **Empty `domain:`** or `domain: [other]` — useless for filtering. Pick the
  real domain(s) from the standard list.
- **Stale `status:`** — `status: current` on a doc whose subject was deleted
  six months ago. Mark `outdated` or supersede.
- **`status: draft` on a doc that's been linked from CLAUDE.md for months**
  — promote to `current`.

---

## Pillar 5b — Placement Fit

The placement decision tree from `doc-standards.md`:

```
docs/
├── foundations/   STABLE conceptual models — "what a Companion IS". Rare change.
├── architecture/  Current implementation reality for broader topics.
│   ├── primitives/  The patterns code MUST compose. Has invariants + bypass cost.
│   ├── journey-*.md User-facing flows end-to-end.
│   └── *.md         Thematic architecture docs.
├── adr/           Point-in-time decisions. Immutable (decision part).
├── guides/        How-to guides for humans.
├── vision/        North star / philosophy.
├── plans/         Story plans (`WA-XXX-plan.md`).
└── refactor/, debug/  Transient.
```

### Method

For each file, ask: does the *content* match the *folder*?

- Implementation reality of a broader system → `architecture/<TOPIC>.md`
- Pattern with invariants used in 3+ places → `architecture/primitives/<name>.md`
- Stable conceptual model, rare change → `foundations/<concept>.md`
- Decision and rationale at a point in time → `adr/<NNNN>.md`
- A how-to for humans → `guides/<topic>.md`

### Findings to look for

- **Architecture doc that's actually a foundation** — no implementation
  detail, all conceptual model. Propose move to `foundations/`.
- **Foundation doc that's actually architecture** — file paths and class
  names everywhere. Propose move to `architecture/`.
- **Architecture doc that's actually a primitive** — the doc describes one
  pattern with invariants and a bypass cost. Propose promotion to
  `architecture/primitives/`. Cite the promotion criteria from
  `.doc-architect.yml`.
- **ADR that drifted into "current state" content** — ADRs are immutable
  decisions. If "current state" content is in an ADR, propose extracting
  it to `architecture/` with a forward-link from the ADR (the ADR-0015
  baseline showed this pattern: ADR was promoted to `foundations/3-layer-model.md`
  but the ADR itself didn't say so).

Placement *moves* are `doc-architect` territory — propose them in your
report, but the actual move goes through `/we:docs`.

---

## Pillar 5c — Format Adherence

### Architecture Doc

```markdown
# [Topic Name]

**Purpose:** 1-sentence description
**Key Files:** Most important code paths

## Overview
Mermaid diagram + short explanation

## [Main sections]
IST-description with code references (file_path:line_number)

## SOLL — Next Steps
Short outlook (max 10% of the doc, clearly marked)

## References
Links to related architecture/ docs, guides, ADRs
```

**SOLL rule:** Max 10% of an `architecture/*.md` may be SOLL. Always under
its own `## SOLL` heading. Stale SOLLs (work shipped or abandoned) are
findings — propose deletion or compression to a one-line "Outcome" pointer.

### Journey Doc

`architecture/journey-*.md` requires `type: journey` plus the canonical 5
sections: Entry, Outcome, Steps (numbered), Components Involved (table),
References.

### Primitive Detail Doc

`architecture/primitives/*.md` requires the 8-section structure: Identity,
Boundary, Invariants (each with `file:line` evidence), Bypass Cost, Bypass
Annotation, How to Use, Anti-Patterns, References.

### Findings to look for

- **Architecture doc missing Mermaid overview** — purely textual when a
  diagram would carry the structure.
- **No `## References` section** — forces every reader to manually find
  related docs.
- **SOLL > 10%** — large outlook section in an IST doc.
- **Primitive doc missing Invariants section** — most common drift in
  primitives. Without invariants, it's not a primitive.
- **Code citations without file:line** — `app/companion/being.py` instead of
  `app/companion/core/being.py:147`. Defeats the point of a primitive doc.

---

## Pillar 5d — Cross-Reference Coherence

### What's required

- Every `architecture/*.md` should link related docs in a `## References`
  section.
- Every `architecture/primitives/*.md` should link: its rule, its check
  script, its ADRs, its source code location.
- Index files (`PRIMITIVES.md`, `BYPASS-REGISTER.md`, `foundations/README.md`,
  `adr/README.md`) should list every doc in their scope.
- Promoted ADRs (e.g. ADR-0015 → `foundations/3-layer-model.md`) need a
  forward-link banner near the top of the ADR.

### Findings to look for

- **Doc not in its index** — `architecture/PRIMITIVES.md` doesn't list this
  primitive. Propose index update.
- **Promoted ADR without a forward-link** — reader of the ADR doesn't know
  the IS-state lives elsewhere now (real example: ADR-0015 baseline F2).
- **Dead internal links** — file referenced doesn't exist or moved.
- **References section absent** — propose adding.

---

## Pillar 5e — Duplicate Content Policy

`doc-standards.md` says:

> **Allowed:** Summaries with links, layer-specific adaptations
> **Forbidden:** Copy-paste without reference, repeating parent content
> **Fix:** One source of truth, reference everywhere else.

This sharpens Pillar 3 (Redundancy) for `docs/`:

- Invariants belong in `architecture/primitives/<name>.md`. Other docs cite
  the primitive — they don't restate the invariants. (Real baseline:
  COMPANION-CORE.md duplicated ~50 lines of invariants from
  `companion-gateway-being.md` primitive.)
- Concepts belong in `foundations/`. Architecture docs reference the
  foundation, they don't redefine the concept.
- Workflows (`how to do X`) belong in `guides/` or in a single rule. Not in
  multiple architecture docs.

### Findings to look for

- **Architecture restating primitive invariants** — propose trimming to
  one-line cite + link.
- **Architecture restating foundation concepts** — same fix.
- **Two architecture docs covering the same flow** — propose merge or split
  by audience.

---

## Output additions for `docs/` files

The verdict line for `docs/` files includes:

```
**Doc meta:** type: <type> · domain: [<list>] · status: <status> · <line count> lines
**Frontmatter:** valid | missing | invalid (<which fields>)
```

If frontmatter is missing or invalid, that's at minimum a MAJOR finding (it
breaks TurboVault discovery). Propose the exact frontmatter to add as part
of the diff.
