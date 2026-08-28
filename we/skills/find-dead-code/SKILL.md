---
name: find-dead-code
description: >
  Finds and removes dead code in Python backends (method-level, test-only, vulture, coverage).
  Triggers: "/we:find-dead-code", "find dead code".
---


# Find Dead Code

Remove dead code from a Python backend systematically.

**Core principle:** Code that is only referenced from tests is dead. The tests validate behavior nobody uses. Find it by searching production code only — if nothing in the app calls it, delete both the code and the test.

---

## Detecting the Source Root

Detect the source and test directories instead of assuming `app/` — the first of `app/`, `src/`,
`lib/` that exists, and `tests/` or `test/`. Every phase below operates on those two.

---

## Workflow

### Phase 1 — Class method reachability (primary tool)

Search for methods with zero production callers:

```bash
# For each class method, check if anything in the source (excluding tests) calls it
grep -rn "def method_name" "$SRC_DIR"/ --include="*.py"
grep -rn "\.method_name(" "$SRC_DIR"/ --include="*.py" | grep -v "$TEST_DIR/" | grep -v "__pycache__"
```

If the project has a `find_dead_methods.py` script, use it. Otherwise, manually check methods in service classes, CRUD modules, and core logic.

**Triage each finding:**

| Signal | Verdict |
|--------|---------|
| Method only called from tests | Dead — delete method AND test |
| Decorated with `@field_validator` / `@model_validator` | Keep (Pydantic framework-called) |
| FastAPI route (`@router.get/post/...`) | Keep (registered via decorator) |
| Django view, management command | Keep (framework-called) |
| Only called via dynamic dispatch (`getattr`, dict lookup) | Keep (verify before deleting) |
| Has "interface compat" comment | Keep (intentional interface) |

### Phase 2 — Coverage-based detection (0% files)

Coverage detection requires `pytest-cov`. Skip this phase if not installed:

```bash
if python -c 'import pytest_cov' 2>/dev/null; then
  COVFLAG="--cov=$SRC_DIR --cov-report=term"
  pytest "$TEST_DIR"/unit/ $COVFLAG -q --tb=no --no-header 2>&1 | grep " 0.00%"
else
  echo "SKIP Phase 2: pytest-cov not installed — coverage detection unavailable"
fi
```

Files at **0% coverage** are never executed — strong dead code candidates.

Verify with grep: does anything in the source import the 0% file?

```bash
grep -rn "from ${SRC_DIR//\//\.}.path.to.module" "$SRC_DIR"/ --include="*.py" | grep -v "__pycache__"
```

Zero results = dead. Delete it.

### Phase 3 — Test-only reference detection

Find code that IS executed by tests but has no production callers:

```bash
# For each module, check if any production code imports it
for f in $(find "$SRC_DIR"/ -name "*.py" -not -path "*/migrations/*" -not -name "__init__.py"); do
  module=$(echo "$f" | sed 's|/|.|g' | sed 's|\.py$||' | sed "s|^${SRC_DIR//./\\.}\.||")
  prod_refs=$(grep -r "$module" "$SRC_DIR"/ --include="*.py" -l | grep -v "$f" | grep -v "__pycache__" | wc -l)
  if [ "$prod_refs" -eq 0 ]; then
    test_refs=$(grep -r "$module" "$TEST_DIR"/ --include="*.py" -l 2>/dev/null | wc -l)
    if [ "$test_refs" -gt 0 ]; then
      echo "TEST-ONLY: $f (imported by $test_refs test files, 0 prod files)"
    fi
  fi
done
```

**Monkeypatch-only** is subtle: `patch("app.services.foo.bar")` makes `bar` appear referenced, but it's only being mocked. If `bar` has zero REAL callers, it's dead.

### Phase 4 — Vulture (80% confidence only)

Run vulture at `--min-confidence 80`, excluding migrations. **Never below 80** — the output becomes
mostly noise and the triage costs more than the deletions save.

Always-skip false positives: anything a framework calls rather than your code —
decorator-registered routes and validators, middleware hooks, management commands — plus
`TypedDict` fields, enum members used only in type positions, and `TYPE_CHECKING` imports.

### Phase 5 — Test cleanup & quality gate

```bash
# Find broken test imports
grep -r "deleted_symbol\|DeletedClass" "$TEST_DIR"/ --include="*.py" -l

# Fix, then validate (use whichever formatter the project ships)
if command -v ruff &>/dev/null; then ruff check . --fix && ruff format .; fi
pytest "$TEST_DIR"/unit/ -x --tb=short -q
```

### Phase 6 — Iterate

Deleting code can expose new dead code. **Always re-run Phase 1 after each batch deletion** until the output is clean.

---

## Common mistakes

- **Treating test refs as real usage** — delete both code and test
- **Missing monkeypatch-only refs** — check actual callers, not mock targets
- **Deleting dynamically-dispatched methods** — check for `getattr`, dict dispatch
- **Running vulture below 80%** — too many false positives
- **Not iterating** — deletion exposes more dead code
