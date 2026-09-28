---
name: find-dead-code
description: >
  Finds and removes dead code in Python backends (method-level, test-only, coverage, vulture).
  Triggers: "/we:find-dead-code", "find dead code".
---

# /we:find-dead-code

Code referenced only from tests is dead: delete it together with its tests. Search production code
only. Source root = the first of `app/`, `src/`, `lib/` that exists; tests = `tests/` or `test/`.
Search with `rg` or the repo's code graph (when the instruction files name one, ask it for callers
first), never `grep -r`: a gitignored graph or cache JSON under the source tree floods the output.

## Phases

1. **Methods without production callers.** For each method in services, CRUD and core modules:
   `rg -n "\.<name>\(" "$SRC" -g '*.py'`. A repo script for this (`find_dead_methods.py` or similar)
   comes first. Keep what a framework calls: Pydantic validators, route and signal decorators,
   management commands, middleware hooks, dynamic dispatch (`getattr`, dict lookup), anything
   annotated as an intentional interface.
2. **0 % coverage files**, only when `pytest-cov` is installed:
   `pytest "$TEST"/unit --cov="$SRC" --cov-report=term -q --tb=no | rg ' 0\.00?%'`. Confirm with
   `rg` that nothing in `$SRC` imports the file; zero importers → delete.
3. **Test-only modules.** Per module, count importers in `$SRC` (excluding itself) and in `$TEST`:
   zero production importers and at least one test importer → dead. A `patch("pkg.mod.fn")` target
   is a mock, not a caller.
4. **vulture** at `--min-confidence 80`, migrations excluded; never lower, the rest is noise. Skip
   `TypedDict` fields, enum members used only in annotations and `TYPE_CHECKING` imports.
5. **Clean up and gate.** `rg -l "<deleted symbol>" "$TEST"`, fix the imports, then the repo's
   formatter and linter and the affected unit tests by name.
6. **Repeat phase 1** after every deletion batch until it comes back empty: a deletion exposes the
   next layer.

When the repo carries a dead-code gate (for example a `scripts/check-dead-*` script), run it last.
