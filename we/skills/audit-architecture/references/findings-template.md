---
name: audit-architecture-findings-reference
description: Output skeleton for the audit findings file — frontmatter, healthcheck section, severity-grouped findings, per-subsystem Mermaid diagrams, optionals doc-refresh, severity scale, filename convention. Loaded on demand by the audit-architecture skill.
---

# Findings-MD Template

Copy this skeleton when writing the output to
`<findings_dir>/YYYY-MM-DD-<scope>.md`. Replace `<...>` placeholders.

````markdown
---
type: audit
domain: [platform]
status: current
created: <YYYY-MM-DD>
scope: <full | "id1,id2,..." | healthcheck>
---

# Architecture Audit — <YYYY-MM-DD>

**Scope:** <full | "ids list" | healthcheck-only>
**Run-Zeit:** <duration>
**Subsysteme audited:** <count> / <total>
**Primitives berührt:** <count> / <total>

## Healthcheck

### Doc-Drift

<table from healthcheck Check 1, or "alle Primitive-Docs grün">

### Bypass-Register-Drift

<table from healthcheck Check 2, or "Register stimmt mit Code überein">

### Missing-Primitive-Scan

<output from scan-recent-primitives.sh>

## Subsystem Findings (priorisiert)

### CRITICAL (<count>)

<bullet list of CRITICAL findings using the per-finding template>

### MAJOR (<count>)

<...>

### MINOR (<count>)

<...>

### NIT (<count>)

<...>

## Per-Subsystem Diagramme

Each deep-audit subsystem gets one block. Inline Mermaid for GitHub
readability, plus link to source `.mmd`.

### <Subsystem Name>

```mermaid
<actual mermaid content>
```

[Source](../architecture/diagrams/<subsystem-id>.mmd)

## Optionals — Doku-Refresh

<for each architecture_doc in optionals subsystem, /we:doc-improve summary>

- ARENA.md: <2 Verbesserungsvorschläge | aktuell, keine Drift>
- ADMIN-SUPPORT.md: <...>
- DATA-MODEL.md: <...>
- ERROR-HANDLING.md: <...>
- FEEDBACK.md: <...>

## Open Items from Previous Audits

<scan docs/audits/*.md for findings still relevant>

- <date>:<finding-title> — still open, see [<file>](<file>)
````

## Per-Finding Template

For each finding under CRITICAL / MAJOR / MINOR / NIT:

```markdown
#### [<subsystem-name>] <Title>: `<file>:<line>`

**Lens:** <Kapselung | Schichten | Primitive-Compliance | Security | Observability | Error-Handling | Tests | Privacy-*>
**Befund:** <one sentence>
**Risiko:** <one sentence>
**Fix:** <one sentence — what to do, not how>
**Aufwand:** <X min | X h>
```

## Severity Scale

| Severity | Definition |
|---|---|
| **CRITICAL** | Security or data-loss risk; broken Primitive invariant; production blocker |
| **MAJOR** | Architectural violation that compounds (skip-layer import, undocumented bypass, no Privacy-Lens coverage of a stated promise) |
| **MINOR** | Code-smell that doesn't break anything (low coverage, missing structlog adoption, unused export) |
| **NIT** | Style, naming, comment quality — fix-when-touching |

## Filename Convention

- `<scope>=full` → `YYYY-MM-DD-full.md`
- `<scope>=<id>` → `YYYY-MM-DD-<id>.md` (e.g. `2026-04-26-tools-skills.md`)
- `<scope>=<id1>,<id2>` → `YYYY-MM-DD-<id1>-<id2>.md` (commas → hyphens)
- `--healthcheck-only` → `YYYY-MM-DD-healthcheck.md`
