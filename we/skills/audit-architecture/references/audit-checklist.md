---
name: audit-architecture-checklist-reference
description: Phase 2 lens checklist for subsystem deep-read — encapsulation, layering, primitive-compliance, security, observability, error-handling, tests, plus the diff-against-previous-diagram check and extra_lens activation
type: reference
---

# Phase 2: Subsystem Deep-Read Checklist

For each `deep-audit` subsystem in scope, the skill performs:

1. **Render Mermaid diagram** to `<diagrams_dir>/<id>.mmd` (with severity-overlay per `visualization.md`)
2. **Diff against previous diagram** (if exists) — structural changes = findings
3. **Run default lens checklist** (the 7 lenses below)
4. **Run extra lenses** declared in subsystem's `extra_lens:` (e.g., `personality-cohesion` for `companion-core`)
5. **Cross-reference Phase-1 hotspots** within this subsystem's path scope

Each lens produces 0..N findings. All findings collected in `<findings_dir>/<date>-<scope>/subsystems/<id>.md`.

## Diff Against Previous Diagram

**Question:** Has the architecture changed since the last audit? Are the changes intentional?

**How to check:**

1. If `<diagrams_dir>/<id>.mmd` already exists in git history, compare the new render against the previous version.
2. Treat each delta:
   - Added/removed top-level node (subgraph or flowchart node) → MAJOR (structural change)
   - Added/removed edge → MINOR (data-flow change)
   - Renamed node only → NIT
   - Severity-class change only → expected (Phase 2 always reapplies)

**Finding template:**

```markdown
### <id>-MAJ-N — Structural drift since last audit

**Severity:** MAJOR
**Lens:** schichten (or: kapselung if a private boundary moved)
**Cite:** `<diagrams_dir>/<id>.mmd` (current vs HEAD~)

The diagram changed:
- New node: `services/foo_service.py` (composition added in last 6mo)
- Removed edge: `crud/foo.py → models/foo.py` (legitimate? — DB shape changed?)

If the change is intentional and architecturally sound: update the
`docs/architecture/<id>.md` doc to describe the new structure, then
the next audit run will pass clean.

**Effort:** S (15-30 min — verify intent + update arch-doc).
```

If no previous diagram exists, this check produces no finding (first-time audit baseline).

## Standard Lenses (apply to all deep-audit subsystems)

### Lens 1: Encapsulation (`kapselung`)

**Question:** Does the subsystem have a clear public API? Are internals imported from outside?

**How to check:**

- Find all imports referencing the subsystem's `paths:` from outside.
- Flag any import that reaches *into* a sub-module (e.g. `from app.companion.core._langgraph import X` is a leak — underscore prefix means private).
- Public surface should be at most a handful of named exports per package.

**Note on cross-subsystem coverage:** This lens is per-subsystem; a leak FROM a subsystem might be invisible if the importing file is in another subsystem's scope. The Phase-3 `encapsulation-boundaries` lens does the project-wide grep that catches these. See `references/encapsulation-boundaries.md`.

**Finding template:**

```markdown
### <id>-MAJ-N — Encapsulation breach: <importing-file>

**Severity:** MAJOR
**Lens:** kapselung
**Cite:** `<importing-file>:<line>`

`<importing-file>` imports `<private-symbol>` from this subsystem's
internal `_*` module. The convention says these are private.

**Fix:** Add the symbol to the package's public API, or stop importing
it from outside.

**Effort:** S-M (15min - 2h depending on call-site count).
```

### Lens 2: Layering (`schichten`)

**Question:** Are Gateway → Service → CRUD → DB access cleanly separated? No skip-layer imports?

**How to check:**

- API/Gateway code should call Services. Services call CRUD. CRUD calls DB.
- Flag any API code that imports from `app/db/` or runs raw `select(Model)` outside the CRUD layer.
- Flag any Service that imports from API routers.
- Cross-reference with the project's `check-crud-bypass.sh` results.

**Finding template:** as above. Severity: MAJOR for skip-layer, MINOR for inverted dependencies.

### Lens 3: Primitive-Compliance

**Question:** Are all touched primitives (subsystem.primitives in YAML) used correctly? Bypasses annotated?

**How to check:**

- For each primitive listed in the subsystem's YAML entry, read the primitive detail doc (`docs/architecture/primitives/<id>.md`) → Invariants section.
- For each invariant, verify in the subsystem's paths.
- Cross-check `BYPASS-REGISTER.md` for entries in this subsystem.

**Synergy with Phase-3:** the `doc-vs-reality-drift` cross-cutting lens runs the same invariant verification project-wide. This per-subsystem check focuses on invariants that are SCOPED to the subsystem.

### Lens 4: Security

**Question:** Trust boundaries clear? Auth chain correct? Multi-tenancy isolated?

**How to check:**

- Are all routes properly guarded (auth dependency)?
- Are RLS contexts set before any query?
- Is user input validated (Pydantic schemas)?
- Are secrets read via `ConfigService`, not `os.environ` directly?

### Lens 5: Observability

**Question:** Structured logs? Metrics? Traces? No PII?

**How to check:**

- Search for `print(` in subsystem paths → MAJOR finding (cross-ref `observability-triad.md` I1).
- Search for raw `logging.getLogger` instead of the project's structured-logger primitive → MAJOR (a recurring real-world finding pattern in observability audits).
- Check that LLM calls go through `InstrumentedChatModel`.
- Search for `logger.{info,error,warning}(f"…")` → MAJOR (cross-ref `observability-triad.md` I2).
- Spot-check log lines for PII (email, phone, raw user_id without hash) → CRITICAL if found.

### Lens 6: Error-Handling

**Question:** `APIError` + `ErrorType` enum, no bare `HTTPException`?

**How to check:**

- Search for `HTTPException(` outside the API error helpers → MAJOR finding (unless `# PRIMITIVE-BYPASS-OK` is on or above the line).
- Verify error catch blocks do not swallow exceptions silently (`except Exception: pass` without explanation).
- Cross-reference with the project's `check-primitive-bypass.sh` results.

### Lens 7: Tests

**Question:** Coverage ≥ 80% (Backend)? Critical paths integration-tested? Each primitive invariant has a test?

**How to check:**

- Run `cd apps/backend && poetry run pytest --cov=app/<subsystem-path>` if available.
- Note the coverage number; flag <80% as MINOR.
- For each primitive invariant in scope: search for a test that asserts it. Map invariant-to-test. Missing mapping = MINOR.
- Look for unit-only paths that should have integration tests (e.g., anything touching DB sessions or LLM calls).

## Extra Lenses (declared per-subsystem)

If a subsystem's YAML entry has `extra_lens: [name1, name2]`, those lenses run additionally in Phase 2 alongside the 7 standard ones.

**Available extra lenses:**

- `personality-cohesion` — Companion-as-Person verification. See `references/personality-cohesion.md`.
- `privacy` — GDPR / data-residency / encryption / tenant-isolation. See § Privacy below.

The skill checks `references/<lens-name>.md` for the lens's method + output format. New lenses are added by writing the reference file + registering in `lens-library.md`.

## Privacy-Lens (declared via `extra_lens: privacy`)

Typically applied to subsystems with `domain: [billing, data-residency]`.

### Privacy-Lens 1: Data residency

**Question:** EU region for all state-bearing services? BYOK path correct?

**How to check:**

- Verify Supabase project is `eu-central-*` (or the project's documented region).
- Verify any third-party provider configs (Anthropic, OpenAI, Deepgram, ElevenLabs) explicitly use EU endpoints where available.
- Verify BYOK promotion logic (`byok-promotion` primitive) covers all promotable sources (CHAT, UTILITY, PROXY).

### Privacy-Lens 2: Encryption

**Question:** Per-User-Encryption at-rest? TLS in-transit? Key-Rotation?

**How to check:**

- Encrypted columns in DB models — search for `Encrypted` SQLAlchemy types or `encrypt(` calls in CRUD.
- Confirm migration adds encryption to new sensitive columns.

### Privacy-Lens 3: GDPR deletion

**Question:** Deletion path implemented? Soft-delete vs. hard-delete clear? Backups?

**How to check:**

- Read the user-deletion code path (likely in `services/billing/` or `crud/user.py`).
- Verify cascading deletion of memories, threads, voice sessions.
- Note whether backups are scrubbed (or document that they aren't, as a known finding).

### Privacy-Lens 4: Tenant-Isolation

**Question:** RLS active? Cross-tenant queries auditable?

**How to check:**

- Verify RLS is enabled on every multi-tenant table (admin queries excepted, but those must be `# CRUD-BYPASS-OK`).
- Verify `set_user_context()` (or equivalent) is called before each request (Auth Context Chain).

### Privacy-Lens 5: Data promise

**Question:** Does the code match the data-protection promise (e.g. from `docs/vision/PHILOSOPHY.md`)?

**How to check:**

- Read the privacy-related sections of the project's vision/philosophy docs.
- For each promise (e.g. "your conversations stay yours"), find the code that enforces it. If you can't find it, that's a CRITICAL finding.

## Cross-Reference with Phase 1 Hotspots

After running the 7 standard lenses + extra lenses for a subsystem, the skill checks: are any files in the subsystem's `paths:` flagged as **unexpected hotspots** in Phase 1?

If yes, surface them in the subsystem's findings MD with a cross-reference to the Phase-3 `architectural-significance` finding (which contains the deep-dive analysis). This connects "files we audited per-subsystem" with "files Phase 1 surfaced as architecturally significant".

Example cross-reference (in subsystem MD):

```markdown
## Phase-1 hotspot cross-references

The following files in this subsystem appeared in Phase-1 top-15 as
**unexpected hotspots** (see `architectural-significance` lens findings
in `cross-cutting.md`):

- `<backend>/api/<endpoint>.py` (Phase-1 score 240, rank #2)
  → Phase-3 finding: AS-MAJ-1 (god-object candidate)
```
