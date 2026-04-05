---
name: find-dead-code
description: >
  Find and remove dead code from Python backends. Covers method-level detection,
  test-only reference detection, vulture static analysis, and coverage-based detection.
  Use when asked to find dead code, clean up unused functions, or reduce codebase size.
---

<!-- SKILL LOADED — Do NOT call Skill(skill="find-dead-code") again. You ARE inside the skill. Start below. -->

# Find Dead Code

Remove dead code from a Python backend systematically.

**Core principle:** Code that is only referenced from tests is dead. The tests validate behavior nobody uses. Find it by searching production code only — if nothing in the app calls it, delete both the code and the test.

---

## Workflow

### Phase 1 — Class method reachability (primary tool)

Search for methods with zero production callers:

```bash
# For each class method, check if anything in the app (excluding tests) calls it
grep -rn "def method_name" app/ --include="*.py"
grep -rn "\.method_name(" app/ --include="*.py" | grep -v "tests/" | grep -v "__pycache__"
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

```bash
pytest tests/unit/ --cov=app --cov-report=term -q --tb=no --no-header 2>&1 | grep " 0.00%"
```

Files at **0% coverage** are never executed — strong dead code candidates.

Verify with grep: does anything in the app import the 0% file?

```bash
grep -rn "from app.path.to.module" app/ --include="*.py" | grep -v "__pycache__"
```

Zero results = dead. Delete it.

### Phase 3 — Test-only reference detection

Find code that IS executed by tests but has no production callers:

```bash
# For each module, check if any production code imports it
for f in $(find app/ -name "*.py" -not -path "*/migrations/*" -not -name "__init__.py"); do
  module=$(echo "$f" | sed 's|/|.|g' | sed 's|\.py$||' | sed 's|^app\.||')
  prod_refs=$(grep -r "$module" app/ --include="*.py" -l | grep -v "$f" | grep -v "__pycache__" | wc -l)
  if [ "$prod_refs" -eq 0 ]; then
    test_refs=$(grep -r "$module" tests/ --include="*.py" -l | wc -l)
    if [ "$test_refs" -gt 0 ]; then
      echo "TEST-ONLY: $f (imported by $test_refs test files, 0 prod files)"
    fi
  fi
done
```

**Monkeypatch-only** is subtle: `patch("app.services.foo.bar")` makes `bar` appear referenced, but it's only being mocked. If `bar` has zero REAL callers, it's dead.

### Phase 4 — Vulture (80% confidence only)

```bash
vulture app/ --min-confidence 80 --exclude "app/db/migrations"
```

At 80%, false positive rate is low. **Do NOT run below 80%** — produces mostly noise.

**Common false positives (always skip):**

- FastAPI/Django route functions (decorator-registered)
- Pydantic validators (`@field_validator`, `@model_validator`)
- Framework middleware hooks
- `TypedDict` field definitions
- `Enum` values in type hints
- `TYPE_CHECKING` imports

### Phase 5 — Test cleanup & quality gate

```bash
# Find broken test imports
grep -r "deleted_symbol\|DeletedClass" tests/ --include="*.py" -l

# Fix, then validate
ruff check . --fix
ruff format .
pytest tests/unit/ -x --tb=short -q
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
