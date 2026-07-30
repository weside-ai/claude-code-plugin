---
name: audit-architecture-subsystems-reference
description: Full schema for `docs/.audit-architecture.yml` (v3) — subsystems, lens activation, hotspot config, personality_cohesion config; backward-compatible with v2
type: reference
---

# Audit Configuration Reference

The skill reads `docs/.audit-architecture.yml` from the **repo root** at the start of every run. This document describes the v3 schema.

**Backward compatibility:** v2 configs (just `findings_dir`, `diagrams_dir`, `healthcheck`, `subsystems`) work unchanged on v3. All v3-additions are optional; the skill default-loads sensible defaults when sections are missing.

## Schema at a Glance

Top-level keys of `docs/.audit-architecture.yml` — each is specified in its own section below
(the sections are the owners; this list is just the map):

```yaml
findings_dir: docs/audits/                    # REQUIRED (v2)
diagrams_dir: docs/architecture/diagrams/     # REQUIRED (v2)
healthcheck: {...}                            # Phase 0 — § Healthcheck Schema
backend_root: <path>                          # NEW v3 — hotspot scan root; SET THIS (see below)
default_lenses: [...]                         # NEW v3 — § Lens-Activation Schema
cross_cutting: [...]                          #          "
optional_lenses: [...]                        #          "
hotspots: {...}                               # NEW v3 — § Hotspot Schema
personality_cohesion: {...}                   # NEW v3 opt-in — § Personality-Cohesion Schema
subsystems: [...]                             # v2, extended — § Subsystem Schema
```

## Healthcheck Schema (unchanged from v2)

```yaml
healthcheck:
  doc_drift:
    enabled: true|false
    target_glob: "docs/architecture/primitives/*.md"
  bypass_register_drift:
    enabled: true|false
    register_path: "docs/architecture/BYPASS-REGISTER.md"
    generator_script: "scripts/generate-bypass-register.sh"
  missing_primitive_scan:
    enabled: true|false
    pr_count: 100
    repo_paths:
      - <backend>/
    keyword_patterns:
      - "introduce"
      - "centralize"
      - "factory"
```

If any check has `enabled: false`, skip it and write `(disabled in config)` in its master.md section.

## Lens-Activation Schema (NEW v3)

```yaml
default_lenses:        # Phase 2, run for every deep-audit subsystem
  [<list of lens-names>]
cross_cutting:         # Phase 3, run project-wide
  [<list of lens-names>]
optional_lenses:       # Phase 3 opt-in only (via --lens= or extra_lens:)
  [<list of lens-names>]
```

**Defaults if missing:** the skill loads:

```yaml
default_lenses: [encapsulation, layering, primitive-compliance, security, observability, error-handling, tests]
cross_cutting:  [encapsulation-boundaries, architectural-significance, doc-vs-reality-drift]
optional_lenses: []
```

Available lens names: see `references/lens-library.md`.

## Hotspot Schema (NEW v3)

```yaml
hotspots:
  top_n: <int>                                  # default 15
  since: <git-log-since-string>                 # default "6 months ago"
  expected_hubs:                                # files marked as documented hubs
    - <relative path>
  encapsulation_homes:                          # used by audit-hotspots.py + encapsulation-boundaries lens
    <vendor>:
      - <home-path-1>
      - <home-path-2>
  private_module_root: <relative path>          # used for `_*` private reach-in detection
  primitive_detectors:                          # project-specific override of plugin's primitives.default.yml
    - name: <primitive-name>                    # (this exact key — audit-hotspots.py reads `primitive_detectors`)
      patterns:
        - <regex>
```

If `hotspots:` is omitted entirely, Phase 1 still runs with skill defaults (top_n=15, since="6 months ago", no expected_hubs → every hotspot is "unexpected").

## Personality-Cohesion Schema (NEW v3, opt-in)

Required ONLY if `personality-cohesion` is in `optional_lenses` AND activated (via `--lens=` or
`extra_lens:`). The full commented block (`identity_construction_paths`, `five_components_map`,
`forbidden_outside_consciousness`) is owned by `references/personality-cohesion.md` § Project
Configuration. If the lens is activated but the block is missing, the skill errors out — there
is no useful default for what "personality" means in any given project.

## Subsystem Schema (extended v3)

```yaml
- id: <kebab-case-id>                           # required, unique, used as CLI argument
  name: "<Human Name>"                          # required, used as section heading
  mode: deep-audit | docs_only                  # required
  architecture_docs:                            # optional, list of filenames in docs/architecture/
    - FOO.md
  primitives:                                   # optional, list of primitive ids
    - foo
  paths:                                        # optional, real existing dirs
    - <backend>/foo/
  extra_lens:                                   # NEW v3: list (was string in v2)
    - personality-cohesion                      # any lens name from optional_lenses
    - privacy
```

**v3 change:** `extra_lens:` is now a **list**. v2 syntax `extra_lens: privacy` (string) is still accepted and converted to `[privacy]` internally.

**Validation rules:**
- `id` must match `^[a-z][a-z0-9-]+$`.
- `mode` must be one of the two enums.
- `paths` entries must exist at run time. If a path is intentionally missing (e.g., code is distributed across many dirs), leave the field empty and add a YAML comment explaining why.
- Empty `architecture_docs:` is allowed and **becomes a finding** in Phase 2 ("missing thematic documentation"). Use this when the gap is intentional and known.
- `extra_lens` entries must be names of lenses listed in `optional_lenses:` (or `default_lenses:` — though there's no point repeating defaults).

## Reading the YAML at Run-Time

Load it with PyYAML, then apply the v3 defaults for any missing `default_lenses` /
`cross_cutting` / `optional_lenses` (values in § Lens-Activation Schema above) and coerce a
string `extra_lens` to a one-item list. Split the subsystems by `mode` — `deep-audit` drives
Phase 2, `docs_only` gets a diagram + doc review only.

**An unknown id fails loudly.** A CLI scope naming a subsystem the YAML does not define, or a
`--lens=` naming an unregistered lens, aborts with the list of valid names — silently auditing a
subset the user did not ask for is worse than not running.

## Reading `.doc-architect.yml` (read-only)

When the missing-primitive-scan flags a candidate, evaluate against the promotion criteria from `docs/.doc-architect.yml`:

```yaml
promotion_to_primitive:
  min_usages: 3
  requires_invariants: true
  requires_bypass_cost: true
```

Don't duplicate this into the audit YAML — read it directly.

## Set `backend_root` explicitly — the shipped defaults assume one layout

`scripts/audit-hotspots.py` and `scripts/primitives.default.yml` carry defaults taken from the
project the skill grew up in (`backend_root`, `encapsulation_homes`, `private_module_root`). On any
other repo they scan the wrong tree or match nothing, and Phase 1 then reports a clean heatmap for
a codebase it never read. **Set `backend_root` in your YAML, and override
`hotspots.primitive_detectors` + `encapsulation_homes` with your own patterns** — a density map
built on someone else's primitives is decoration.

## Migration from v2 to v3

A v2 config runs unchanged on v3. To opt into the v3 features, append: `backend_root`, a
`hotspots:` block (`top_n`, `since`, `expected_hubs`), and — for a Companion-style architecture —
`optional_lenses: [personality-cohesion]` plus the `personality_cohesion:` block from
`references/personality-cohesion.md`, activated per subsystem via `extra_lens:`.
