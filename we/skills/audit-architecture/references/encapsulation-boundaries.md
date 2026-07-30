---
name: audit-architecture-encapsulation-boundaries
description: Phase 3 default lens — exhaustive grep for cross-module imports that violate encapsulation rules
type: reference
---

# Encapsulation Boundaries (Phase 3, default)

## Purpose

Verify the project's documented encapsulation rules at the import level, **across the entire codebase** (not just within one subsystem). Catches leaks that subsystem-bounded audits miss because they only grep within one subsystem's `paths:`.

## When to apply

- **Phase 3** of `/we:audit-architecture` — runs by default in `cross_cutting:` lenses.
- **Standalone:** `--lens=encapsulation-boundaries`
- **Project requirement:** project must declare which paths are "homes" for which vendor imports + the private-module root for `_*` enforcement (in `hotspots.encapsulation_homes:` and `hotspots.private_module_root:`).

## Project Configuration

```yaml
hotspots:
  encapsulation_homes:
    <vendor-import-prefix>:
      - <the/one/layer/that/may/import/it>/
      - <and/its/factory.py>
  private_module_root: <backend>/<agent-core>
```

The catalog (`primitives.default.yml`) ships with reasonable defaults for Companion-style projects. Project YAML overrides as needed.

## Method

Three sub-checks, each one exhaustive search over the scan root. What matters is not the regex —
it is that the search runs over the **whole** codebase, because a subsystem-scoped audit only ever
greps inside one subsystem's `paths:` and structurally cannot see a leak that crosses them.

### EB-1 — Vendor runtime imports

For every vendor in `encapsulation_homes`: find its runtime imports and check each against that
vendor's configured home paths. Matches outside every home are findings.

| Case | Severity |
|---|---|
| One or more violations in a file | MAJOR — one finding per file, not per line |
| `TYPE_CHECKING`-only import | MINOR — never executes, but the name still leaks into the surface |

**Fix shape:** move the construction that needs the vendor *into* the home; the outer file consumes
an abstraction the home returns, not the vendor's own type.

### EB-2 — Private-module reach-ins

Find imports of `_`-prefixed symbols from inside `private_module_root` made by files outside it.
Only siblings within the root may import them. MAJOR per importing file (combine its imports into
one finding).

**Fix shape:** expose the symbol properly (rename, document), push the consumer inside the root, or
find a different abstraction. Three choices, all better than the reach-in.

### EB-3 — Transport-layer type construction

Where the project treats its channel/transport modules as THIN (parse in, format out, route on),
find agent-framework message types being *constructed* inside them. A framework type built in a
transport means the framework has leaked into the transport → MAJOR. No THIN-channel convention in
this project → this sub-check produces nothing.

## Output Format

```markdown
### EB-MAJ-N — <vendor> runtime import in <file>

**Severity:** MAJOR
**Lens:** encapsulation-boundaries
**Sub-check:** EB-1 (Vendor Runtime-Imports)
**Cite:** `<file>:<line>`

<the offending import line>

This file is OUTSIDE the configured homes for `<vendor>` (<the configured home paths>).

**Implication:** when `<vendor>` changes that API — or the project swaps the runtime — this file
breaks. Making that cost zero is the entire purpose of the encapsulation contract.

**Fix:** push the construction into the home and have this file call a home method that returns
whatever shape it actually needs.

**Effort:** M (1-2h per occurrence)
```

## The shapes this lens surfaces

| Shape | Finding |
|---|---|
| A tier that is *supposed* to know nothing about the agent framework imports its message types at runtime — often with a TODO next to it | EB-MAJ |
| A transport-only channel module imports a framework type at runtime | EB-MAJ — THIN-channel violation |
| A `TYPE_CHECKING`-only import of a framework internal | EB-MIN — never executes, still leaks the name |
| Services or tools reaching into another package's `_*` helpers instead of its public API | EB-MAJ per importing file |
| An admin/debug module reaching into internals | usually exemptable — say so explicitly rather than silently passing it |

## Cross-Reference with Phase 1

`audit-hotspots.py` already counts leaks and reach-ins into the score. This lens turns those numbers
into findings — with severity, citation, and a fix.

## Customization

- **Polyglot backend:** add the other language's import patterns to `encapsulation_homes`.
- **No private-module convention:** omit `private_module_root` → EB-2 is skipped.
- **No THIN-transport rule:** EB-3 produces nothing. Both are absences, not failures.

## Why this lens?

Without it, encapsulation findings depend on auditor luck: a vendor-import search run inside one
subsystem catches that subsystem's leak, and reach-ins elsewhere surface only if a different search
happens to be run. Systematic beats lucky.
