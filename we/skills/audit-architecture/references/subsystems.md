---
name: audit-architecture-subsystems-reference
description: Full schema for `docs/.audit-architecture.yml` (v3) — subsystems, lens activation, hotspot config, personality_cohesion config; backward-compatible with v2
type: reference
---

# Audit Configuration Reference

The skill reads `docs/.audit-architecture.yml` from the **repo root** at the start of every run. This document describes the v3 schema.

**Backward compatibility:** v2 configs (just `findings_dir`, `diagrams_dir`, `healthcheck`, `subsystems`) work unchanged on v3. All v3-additions are optional; the skill default-loads sensible defaults when sections are missing.

## Full v3 Schema

```yaml
# REQUIRED (also in v2)
findings_dir: docs/audits/
diagrams_dir: docs/architecture/diagrams/

# Phase 0 healthcheck (also in v2)
healthcheck:
  doc_drift:
    enabled: true
    target_glob: "docs/architecture/primitives/*.md"
  bypass_register_drift:
    enabled: true
    register_path: "docs/architecture/BYPASS-REGISTER.md"
    generator_script: "scripts/generate-bypass-register.sh"
  missing_primitive_scan:
    enabled: true
    pr_count: 100
    repo_paths:
      - apps/backend/app/
    keyword_patterns:
      - "introduce"
      - "centralize"
      - "factory"

# NEW v3: backend-root for hotspot scan (default: apps/backend/app)
backend_root: apps/backend/app

# NEW v3: lens activation (all optional, skill default-loads)
default_lenses:
  - encapsulation
  - layering
  - primitive-compliance
  - security
  - observability
  - error-handling
  - tests
cross_cutting:
  - encapsulation-boundaries
  - architectural-significance
  - doc-vs-reality-drift
optional_lenses:
  - personality-cohesion
  - privacy

# NEW v3: Phase 1 hotspot config (used by audit-hotspots.py)
hotspots:
  top_n: 15                          # default 15
  since: "6 months ago"              # git log --since=
  expected_hubs:                     # documented hubs (no surprise)
    - apps/backend/app/main.py
    - apps/backend/app/companion/core/being.py
  encapsulation_homes:               # vendor home-paths for leak detection
    langchain:
      - apps/backend/app/companion/core/
      - apps/backend/app/config/llm.py
    langgraph:
      - apps/backend/app/companion/core/
  private_module_root: apps/backend/app/companion/core
  primitive_detectors_extra: []      # project-specific override of catalog

# NEW v3: optional Personality-Cohesion config (Companion-projects)
personality_cohesion:
  identity_construction_paths:
    - apps/backend/app/companion/core/consciousness.py
    - apps/backend/app/companion/core/_context_composer.py
  five_components_map:
    CONSCIOUSNESS: [apps/backend/app/companion/core/]
    SENSES:        [apps/backend/app/senses/]
    BODY:          [apps/backend/app/companion/channels/, apps/backend/app/tools/]
    MEMORY:        [apps/backend/app/companion/core/memory.py, apps/backend/app/crud/memory.py]
    EXPERIENCE:    [apps/backend/app/services/evolution/]
  forbidden_outside_consciousness:
    - "system_prompt ="
    - "personality ="

# Subsystems (extended v2 schema; new optional fields)
subsystems:
  - id: <kebab-case-id>
    name: "<Human Name>"
    mode: deep-audit | docs_only
    architecture_docs: [...]
    primitives: [...]
    paths: [...]
    extra_lens: [...]                # NEW v3: list of lens names (was string in v2)
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
      - apps/backend/app/
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
  primitive_detectors_extra:                    # project-specific override of plugin's primitives.default.yml
    - name: <primitive-name>
      patterns:
        - <regex>
```

If `hotspots:` is omitted entirely, Phase 1 still runs with skill defaults (top_n=15, since="6 months ago", no expected_hubs → every hotspot is "unexpected").

## Personality-Cohesion Schema (NEW v3, opt-in)

Required ONLY if `personality-cohesion` is in `optional_lenses` AND activated (via `--lens=` or `extra_lens:`).

```yaml
personality_cohesion:
  identity_construction_paths:                  # required: where identity MAY be constructed
    - <path>
  five_components_map:                          # required: each component's canonical home(s)
    CONSCIOUSNESS: [<path>, ...]
    SENSES:        [<path>, ...]
    BODY:          [<path>, ...]
    MEMORY:        [<path>, ...]
    EXPERIENCE:    [<path>, ...]
  forbidden_outside_consciousness:              # required: patterns that may NOT appear outside identity_construction_paths
    - <pattern>
```

If the lens is activated but the config block is missing, the skill errors out with a helpful message — there is no useful default for what "personality" means in any given project.

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
    - apps/backend/app/foo/
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

Use Python (yaml module). The skill provides a helper that loads + validates + applies defaults:

```python
import yaml
data = yaml.safe_load(open("docs/.audit-architecture.yml"))

# v3 default-loading
data.setdefault("default_lenses", ["encapsulation", "layering", "primitive-compliance",
                                    "security", "observability", "error-handling", "tests"])
data.setdefault("cross_cutting", ["encapsulation-boundaries",
                                   "architectural-significance",
                                   "doc-vs-reality-drift"])
data.setdefault("optional_lenses", [])

# Backward-compat: extra_lens as string → list
for s in data["subsystems"]:
    if isinstance(s.get("extra_lens"), str):
        s["extra_lens"] = [s["extra_lens"]]

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

## CLI Lens Filtering

```python
# /we:audit-architecture --lens=encapsulation-boundaries,personality-cohesion
lens_filter = args.lens.split(",") if args.lens else None
if lens_filter:
    # In Phase 3, only run these lenses
    cross_cutting_to_run = [l for l in (data["cross_cutting"] + data["optional_lenses"])
                             if l in lens_filter]
    unknown = [l for l in lens_filter if l not in (data["cross_cutting"] + data["optional_lenses"])]
    if unknown:
        print(f"Unknown lens names: {unknown}. Available: {data['cross_cutting'] + data['optional_lenses']}")
        raise SystemExit(1)
```

## Reading `.doc-architect.yml` (read-only)

When the missing-primitive-scan flags a candidate, evaluate against the promotion criteria from `docs/.doc-architect.yml`:

```yaml
promotion_to_primitive:
  min_usages: 3
  requires_invariants: true
  requires_bypass_cost: true
```

Don't duplicate this into the audit YAML — read it directly.

## Migration from v2 to v3

A v2 config requires NO changes to run on v3. To take advantage of new v3 features:

```yaml
# Add at the end of the file (anywhere works, YAML is unordered):

backend_root: apps/backend/app          # if not already implicit

hotspots:
  top_n: 15
  since: "6 months ago"
  expected_hubs:
    - <list documented hub files>

# If you have a Companion-style architecture and want personality-cohesion:
optional_lenses: [personality-cohesion]

personality_cohesion:
  identity_construction_paths: [...]
  five_components_map: {...}
  forbidden_outside_consciousness: [...]

# Then in your subsystem entries, optionally:
subsystems:
  - id: companion-core
    extra_lens: [personality-cohesion]
```
