---
name: audit-architecture-subsystems-reference
description: Schema reference for `docs/.audit-architecture.yml` — the project-side config that defines subsystems, modes, paths, healthcheck flags. Loaded on demand by the audit-architecture skill.
---

# Subsystem Configuration Reference

The skill reads `docs/.audit-architecture.yml` from the **repo root** at
the start of every run. This document describes the schema.

## Top-Level Schema

```yaml
findings_dir: <relative-path>            # required, e.g. docs/audits/
diagrams_dir: <relative-path>            # required, e.g. docs/architecture/diagrams/
healthcheck:                             # required object — see below
  doc_drift: ...
  bypass_register_drift: ...
  missing_primitive_scan: ...
subsystems:                              # required list, ≥1 entry
  - id: ...
    ...
```

## Healthcheck Schema

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
    pr_count: 100                        # number of recent PRs to scan
    repo_paths:                          # which dirs to inspect for new patterns
      - apps/backend/app/
    keyword_patterns:                    # regex (POSIX, single-line) — match PR title/body
      - "introduce"
      - "centralize"
      - "factory"
```

If any check has `enabled: false`, skip it and write
"`(disabled in config)`" in its Findings-MD section.

## Subsystem Schema

```yaml
- id: <kebab-case-id>                    # required, unique, used as CLI argument
  name: "<Human Name>"                   # required, used as section heading
  mode: deep-audit | docs_only           # required
  architecture_docs:                     # optional, list of filenames in docs/architecture/
    - FOO.md
  primitives:                            # optional, list of primitive ids (filenames in docs/architecture/primitives/ without .md)
    - foo
  paths:                                 # optional, real existing dirs (skill validates at start)
    - apps/backend/app/foo/
  extra_lens: privacy                    # optional, currently only "privacy" supported
```

**Validation rules:**
- `id` must match `^[a-z][a-z0-9-]+$`.
- `mode` must be one of the two enums.
- `paths` entries must exist at run time. If a path is intentionally
  missing (e.g. code is distributed across many dirs), leave the field
  empty and add a YAML comment explaining why.
- Empty `architecture_docs:` is allowed and **becomes a Finding** in
  Phase 1 ("missing thematic documentation"). Use this when the gap is
  intentional and known.

## Reading the YAML at Run-Time

Use Python (yaml module) to load it. Pseudo:

```python
import yaml
data = yaml.safe_load(open("docs/.audit-architecture.yml"))
deep_audit = [s for s in data["subsystems"] if s["mode"] == "deep-audit"]
docs_only = [s for s in data["subsystems"] if s["mode"] == "docs_only"]
```

## CLI Scope Filtering

```python
# /we:audit-architecture tools-skills,workspace-io
scope = "tools-skills,workspace-io".split(",")
filtered = [s for s in data["subsystems"] if s["id"] in scope]
unknown = [id for id in scope if id not in {s["id"] for s in data["subsystems"]}]
if unknown:
    print(f"Unknown subsystem ids: {unknown}")
    raise SystemExit(1)
```

## Reading `.doc-architect.yml` (read-only)

When the missing-primitive-scan flags a candidate, evaluate against
the promotion criteria from `docs/.doc-architect.yml`:

```yaml
promotion_to_primitive:
  min_usages: 3
  requires_invariants: true
  requires_bypass_cost: true
```

Don't duplicate this into the audit YAML — read it directly.
