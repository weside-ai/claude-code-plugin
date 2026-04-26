---
name: audit-architecture
description: Run a backend architecture, quality, and security audit. Three phases (Healthcheck → Subsystem-Audit → Findings). Auto-pilot mode with optional scope restriction. Use when user types "/we:audit-architecture" or asks to "audit the backend architecture", "check architectural drift", "run an architecture review". Output is a dated Findings-MD plus Mermaid diagrams.
---

# /we:audit-architecture — Backend Architecture Audit

You are running a major Architecture × Quality × Security audit on this
project's backend. The user wants three things:

1. A **healthcheck** that reveals doc-drift, new bypasses, and patterns
   that have grown into Primitive-candidates without anyone noticing.
2. A **subsystem-by-subsystem audit pass** with diagrams, primitive
   compliance, encapsulation, layering, and security lenses.
3. A **prioritised Findings-MD** as audit-trail, plus persistent Mermaid
   diagrams as architecture documentation.

Read [`references/subsystems.md`](references/subsystems.md) first to
understand how the project's `docs/.audit-architecture.yml` works. Then
follow the three phases below.

---

## CLI Surface

```
/we:audit-architecture                            # full run
/we:audit-architecture <id>                       # one subsystem
/we:audit-architecture <id1>,<id2>                # multiple
/we:audit-architecture --healthcheck-only         # only Phase 0
/we:audit-architecture --since=YYYY-MM-DD         # delta — only subsystems whose paths changed since date
/we:audit-architecture --skip-healthcheck         # skip Phase 0 (fast re-runs)
```

`<id>` is the `id:` field from `.audit-architecture.yml`.

---

## Phase 0: Healthcheck

Read [`references/healthcheck.md`](references/healthcheck.md). Three checks:

1. **Doc-Drift** — invoke `/we:doc-improve` over primitive detail docs.
2. **Bypass-Register-Drift** — re-run the generator script, diff against
   committed `BYPASS-REGISTER.md`.
3. **Missing-Primitive-Scan** — call `scripts/scan-recent-primitives.sh`
   with the project's config.

Skip Phase 0 if `--skip-healthcheck`. Run only Phase 0 and stop if
`--healthcheck-only`.

---

## Phase 1: Subsystem-Audit

For each subsystem with `mode: deep-audit` (filtered by CLI scope):

1. **Render Mermaid diagram** to `<diagrams_dir>/<id>.mmd`. Read the
   listed `architecture_docs` and the listed `paths` to derive the
   diagram. If a previous diagram exists, diff against it; structural
   changes become Findings.

2. **Run the lens checklist** from [`references/audit-checklist.md`](references/audit-checklist.md).
   Subsystems with `extra_lens: privacy` get the additional GDPR/residency
   lens.

3. **Collect findings** — each gets Severity (CRITICAL / MAJOR / MINOR /
   NIT), Lens, file:line citation, fix proposal, effort estimate.

For subsystems with `mode: docs_only` (= `optionals`):

- Render diagram (or drift-check if exists)
- Invoke `/we:doc-improve` over the listed `architecture_docs`
- Output: Doku-Refresh-Vorschlag, no findings

---

## Phase 2: Findings-Konsolidierung

Use [`references/findings-template.md`](references/findings-template.md)
to write the output to `<findings_dir>/YYYY-MM-DD-<scope>.md`.

`<scope>` filename rules:
- full run → `full`
- single subsystem → that id (e.g. `tools-skills`)
- multiple → comma-joined (e.g. `tools-workspace`)
- `--healthcheck-only` → `healthcheck`

Diagrams are embedded inline as ` ```mermaid` blocks (so the file is
readable on GitHub) and also linked to their `.mmd` source.

---

## What NOT to do

- Don't auto-fix findings. Output is a recommendation; the user decides.
- Don't commit anything besides the diagrams and the findings file.
- Don't bypass the project's `.audit-architecture.yml` — if the YAML is
  missing, ask the user to create it (point at the spec).
- Don't invent subsystems not in the YAML. The YAML is the source of
  truth for scope.
