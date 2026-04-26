---
name: audit-architecture-checklist-reference
description: Phase 1 lens checklist — encapsulation, layering, primitive-compliance, security, observability, error-handling, tests, plus optional privacy lens for residency-tagged subsystems. Loaded on demand by the audit-architecture skill.
---

# Phase 1: Subsystem-Audit Checklist

For each `deep-audit` subsystem, render the diagram and run **every**
lens below. Each lens produces 0..N findings. Collect all findings
under the subsystem's heading in the Findings-MD.

## Standard Lenses (apply to all deep-audit subsystems)

### Lens 1: Kapselung (Encapsulation)

**Question:** Hat das Subsystem klare Public-API? Werden Internals von
außen importiert?

**How to check:**
- Find all imports referencing the subsystem's `paths:` from outside.
- Flag any import that reaches *into* a sub-module (e.g.
  `from app.companion.core._langgraph import X` is a leak —
  underscore prefix means private).
- Public surface should be at most a handful of named exports per package.

**Finding template:**

```
**[<subsystem-name>] Kapselung-Bruch: <path>:<line>**
**Severity:** MAJOR
**Befund:** <which file imports which private symbol>
**Risiko:** Refactor of internal modules will break unrelated callers.
**Fix:** Add the symbol to the package's public API, or stop importing
it from outside.
**Aufwand:** <minutes>
```

### Lens 2: Schichten (Layering)

**Question:** Gateway → Service → CRUD → DB-Zugriff sauber getrennt?
Keine Skip-Layer-Imports?

**How to check:**
- API/Gateway code should call Services. Services call CRUD. CRUD calls DB.
- Flag any API code that imports from `app/db/` or runs raw `select(Model)`.
- Flag any Service that imports from API routers.

**Finding template:** as above, with `**Severity:** MAJOR` for skip-layer,
`MINOR` for inverted dependencies.

### Lens 3: Primitive-Compliance

**Question:** Sind alle berührten Primitives (subsystem.primitives in
YAML) korrekt verwendet? Bypässe annotiert?

**How to check:**
- For each primitive listed in the subsystem's YAML entry, read the
  primitive detail doc (`docs/architecture/primitives/<id>.md`) →
  Invariants section.
- For each invariant, search the subsystem's paths for violations.
- Cross-check `BYPASS-REGISTER.md` for entries in this subsystem.

### Lens 4: Security

**Question:** Trust-Boundaries klar? Auth-Chain korrekt? Multi-Tenancy
isoliert?

**How to check:**
- Are all routes properly guarded (auth dependency)?
- Are RLS contexts set before any query?
- Is user input validated (Pydantic schemas)?
- Are secrets read via `ConfigService`, not `os.environ` directly?

### Lens 5: Observability

**Question:** Strukturierte Logs? Metriken? Traces? Keine PII?

**How to check:**
- Search for `print(` in subsystem paths → MAJOR finding.
- Search for raw `logging.getLogger` instead of `structlog` → MINOR.
- Check that LLM calls go through `InstrumentedChatModel` (Multi-LLM subsystem).
- Spot-check log lines for PII (email, phone, raw user_id without hash).

### Lens 6: Error-Handling

**Question:** `APIError` + `ErrorType`-Enum, kein nacktes `HTTPException`?

**How to check:**
- Search for `HTTPException(` outside the API error helpers → MAJOR finding
  (unless `# PRIMITIVE-BYPASS-OK` is on or above the line).
- Verify error catch blocks do not swallow exceptions silently.

### Lens 7: Tests

**Question:** Coverage ≥ 80% (Backend)? Critical Paths integration-tested?

**How to check:**
- Run `cd apps/backend && poetry run pytest --cov=app/<subsystem-path>` if available.
- Note the coverage number; flag <80% as MINOR.
- Look for unit-only paths that should have integration tests (e.g.
  anything touching DB sessions or LLM calls).

## Privacy-Lens (only if `extra_lens: privacy`)

Currently applied only to subsystem #14 (`plans-residency`).

### Privacy-Lens 1: Datenresidenz

**Question:** EU-Region für alle State-bearing Services? BYOK-Pfad korrekt?

**How to check:**
- Verify Supabase project is `eu-central-*`.
- Verify any third-party provider configs (Anthropic, OpenAI, Deepgram,
  ElevenLabs) explicitly use EU endpoints where available.
- Verify BYOK promotion logic (`byok-promotion` primitive) covers all
  promotable sources (CHAT, UTILITY, PROXY).

### Privacy-Lens 2: Verschlüsselung

**Question:** Per-User-Encryption at-rest? TLS in-transit? Key-Rotation?

**How to check:**
- Encrypted columns in DB models — search for `Encrypted` SQLAlchemy types
  or `encrypt(` calls in CRUD.
- Confirm migration adds encryption to new sensitive columns.

### Privacy-Lens 3: GDPR-Löschung

**Question:** Löschpfad implementiert? Soft-Delete vs. Hard-Delete klar?
Backups?

**How to check:**
- Read the user-deletion code path (likely in `services/billing/` or
  `crud/user.py`).
- Verify cascading deletion of memories, threads, voice sessions.
- Note whether backups are scrubbed (or document that they aren't, as
  a known finding).

### Privacy-Lens 4: Tenant-Isolation

**Question:** RLS aktiv? Cross-Tenant-Queries auditierbar?

**How to check:**
- Verify RLS is enabled on every multi-tenant table (admin queries
  excepted, but those must be `# CRUD-BYPASS-OK`).
- Verify `set_user_context()` is called before each request (Auth Context Chain).

### Privacy-Lens 5: Datenversprechen

**Question:** Stimmt der Code mit dem Datenschutzversprechen aus
`docs/vision/PHILOSOPHY.md`?

**How to check:**
- Read the privacy-related sections of PHILOSOPHY.md.
- For each promise (e.g. "your conversations stay yours"), find the
  code that enforces it. If you can't find it, that's a CRITICAL finding.
