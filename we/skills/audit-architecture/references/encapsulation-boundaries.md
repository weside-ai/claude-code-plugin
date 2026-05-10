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
    langchain:
      - apps/backend/app/companion/core/
      - apps/backend/app/config/llm.py
      - apps/backend/app/config/_instrumented_model.py
    langgraph:
      - apps/backend/app/companion/core/
  private_module_root: apps/backend/app/companion/core
```

The catalog (`primitives.default.yml`) ships with reasonable defaults for Companion-style projects. Project YAML overrides as needed.

## Method

Three sub-checks (each a single grep):

### EB-1 — Vendor Runtime-Imports

For each `vendor` in `encapsulation_homes`:

```bash
grep -rEn "^\s*from ${vendor}" <backend_root> --include="*.py"
```

Each match is checked against the configured home paths. Matches OUTSIDE all home paths are findings.

**Severity rule:**
- 1 violation in a single file: MAJOR
- Multiple violations in a single file: MAJOR (one finding per file, not per line)
- TYPE_CHECKING-only imports (`if TYPE_CHECKING: from langgraph...`): MINOR (documented intent matters)

**Fix proposal pattern:**
> Move the construction/usage that requires `<vendor>` into the configured home (e.g., `companion/core/`). The current file should consume an abstraction provided by the home, not the vendor type directly.

### EB-2 — Private-Module Reach-Ins

```bash
grep -rEn "from ${private_module_root_python}\._\w+ import" <backend_root> --include="*.py" \
  | grep -v "^${private_module_root}/"
```

(Where `private_module_root_python` is the path-form converted to dotted module form: `apps/backend/app/companion/core` → `apps.backend.app.companion.core`.)

Each match is a file outside the private root importing a `_*` symbol from inside the private root. The convention says these are private — only sibling modules in the same root may import them.

**Severity rule:** MAJOR per importing-file (combine multiple imports from the same file into one finding).

**Fix proposal pattern:**
> Either expose the symbol publicly (rename without leading `_`, document) OR push the consumer into the private root OR find a different abstraction.

### EB-3 — THIN-Channel Vendor Construction

If `encapsulation_homes.langchain` exists, additionally check:

```bash
# Find LangChain message construction in channel transports
grep -rEn "HumanMessage\(|AIMessage\(|SystemMessage\(" <backend_root>/companion/channels/ --include="*.py"
```

Channels are supposed to be THIN transports: parse incoming, format outgoing, route to gateway. Constructing LangGraph message types in a channel = LangGraph type leaking into transport = MAJOR.

This sub-check assumes the project follows the "THIN channel" convention; absent that, this sub-check produces no findings.

## Output Format

```markdown
### EB-MAJ-N — <vendor> runtime import in <file>

**Severity:** MAJOR
**Lens:** encapsulation-boundaries
**Sub-check:** EB-1 (Vendor Runtime-Imports)
**Cite:** `<file>:<line>`

```python
from langchain_core.messages import AIMessage  # noqa: PLC0415
```

This file is OUTSIDE the configured `langchain` home paths
(`apps/backend/app/companion/core/`, `apps/backend/app/config/llm.py`,
`apps/backend/app/config/_instrumented_model.py`).

**Implication:** when LangChain v2 changes the message API or we swap
the agent runtime, this file breaks. The encapsulation contract exists
to make exactly this cost zero.

**Fix:** push the construction into `companion/core/` and have the
current file call a Core method that returns whatever primitive shape
it actually needs.

**Effort:** M (1-2h per occurrence)
```

## What findings look like

Typical shapes a real run produces:

1. **EB-MAJ-1** — A "fat-but-framework-naive" service tier (e.g. a gateway
   that's supposed to know nothing about LangGraph) does a runtime import
   from the framework's message types. Often acknowledged by a nearby TODO.

2. **EB-MAJ-2** — A transport-only channel module (telegram, slack, web,
   etc.) imports a framework-specific message type at runtime. THIN-channel
   violation; channels were typically renamed from generic `adapters/`
   precisely to mark them as transport-only.

3. **EB-MIN-1** — A `TYPE_CHECKING`-only import of a framework-internal
   class. MINOR because it never executes, but it still leaks the name
   into the gateway's surface and is worth tracking.

EB-2 (private reach-ins) typically surface as a table of 5–15 sites where
non-owner modules import a `_private` symbol from another package. Common
shapes:

| Where the reach-in lives | What it reaches in for | Why it's MAJOR |
|---|---|---|
| `services/<various>.py` | helper modules under another package's `_*` namespace | services should call the public API, not the helper |
| `tools/<various>.py` | request-context / loader / cache helpers | the same — public surface only |
| `api/admin/debug.py` | framework internals | usually exemptable as documented admin/debug exception |

## Cross-Reference with Phase 1

The hotspot script (`audit-hotspots.py`) already counts these as `leaks` and `reach_ins` in the score. The encapsulation-boundaries lens makes them findings (with severity, citations, and fix proposals) rather than just numbers in a column.

## Customization

Projects with different conventions adjust:

- **Multiple-language backends:** add language-specific patterns to `encapsulation_homes` (e.g., a Go module path)
- **No private convention:** omit `private_module_root` to skip EB-2
- **No THIN-channel rule:** omit `encapsulation_homes.langchain` channel-specific path to skip EB-3 (or rather, EB-3 only fires if channels paths are configured for langchain home OR if channel files appear in non-channel homes)

## Why this lens?

Without an explicit cross-cutting lens, encapsulation findings depend on
auditor luck — a `from langchain` grep done in one subsystem catches the
gateway leak, while reach-ins into another package's `_private` modules
only surface if a *different* grep happens to be run. This lens makes the
same checks systematic and reproducible.
