---
name: audit-architecture-healthcheck-reference
description: Phase 0 healthcheck mechanics — doc-drift over primitive detail docs, bypass-register-drift via the generator script, and missing-primitive-scan via the helper script. Loaded on demand by the audit-architecture skill.
---

# Phase 0: Healthcheck

Three checks, all deterministic, all reuse existing project tooling.

## Check 1: Doc-Drift in Primitive Detail Docs

**Mechanic:** Invoke `/we:doc-improve` over the glob from
`healthcheck.doc_drift.target_glob` (default: `docs/architecture/primitives/*.md`).

`/we:doc-improve` is a sibling skill that compares each doc against its
referenced code and produces a diff list. We don't apply the diffs — we
just collect them as findings.

**Output format (in the Findings-MD):**

```markdown
### Doc-Drift

| Primitive | Drift | Suggestion |
|---|---|---|
| db-sessions.md | line 42 references `get_admin_session` which no longer exists | rename to `get_tool_session` |
| meter-primitive.md | examples use old `bucket` enum values | update to current enum |
| ... | (no drift found) | — |
```

If `/we:doc-improve` finds nothing: write "alle Primitive-Docs grün" in
the table.

## Check 2: Bypass-Register-Drift

**Mechanic:**

```bash
cd <repo_root>
bash scripts/generate-bypass-register.sh > /tmp/bypass-current.md
diff docs/architecture/BYPASS-REGISTER.md /tmp/bypass-current.md
```

(Script path comes from `healthcheck.bypass_register_drift.generator_script`.)

The committed `BYPASS-REGISTER.md` should equal the freshly-generated one.
If it differs, the codebase has new (or removed) bypasses that the
register file is unaware of.

**Output format:**

```markdown
### Bypass-Register-Drift

| Change | Annotation | File:Line | Reason |
|---|---|---|---|
| NEW | `# CRUD-BYPASS-OK` | app/admin/dashboard.py:88 | "admin cross-user query" |
| REMOVED | `# SESSION-BYPASS-OK` | app/health/probe.py:14 | (was in v3.4.0, gone now) |
```

Plus a recommendation: "Run `bash scripts/generate-bypass-register.sh --write`
to update the committed register" if drift exists.

## Check 3: Missing-Primitive-Scan

**Mechanic:** Call the helper script:

```bash
bash <skill_root>/scripts/scan-recent-primitives.sh \
  --config <repo_root>/docs/.audit-architecture.yml \
  --repo <repo_root> \
  --pr-count 100 \
  --output-md
```

The script returns markdown ready to inline. It uses `gh pr list`,
`jq`, and the `keyword_patterns` from the YAML.

See [`scripts/scan-recent-primitives.sh`](../scripts/scan-recent-primitives.sh)
for the implementation.

**Output format:**

```markdown
### Missing-Primitive-Scan

**Verdachts-Pfade (≥3 PRs in last 100):**

| Path | PR Count | Already a Primitive? |
|---|---|---|
| apps/backend/app/dispatch/ | 8 | ✓ DispatchService |
| apps/backend/app/proactivity/triggers/ | 4 | ⚠ no primitive |

**PR-Schlagwort-Treffer (manuell prüfen):**

- #1718 "introduce SafeDeleteContext" → maybe new primitive?
- #1742 "centralize companion warmup" → likely Companion Lifecycle scope
```

Findings: any ⚠ row OR keyword hit becomes a MAJOR Promotion-Finding
("evaluate against promotion criteria from `.doc-architect.yml`:
min_usages=3, requires_invariants, requires_bypass_cost").

## Aggregating into Findings-MD

The three sections above all live under a top-level `## Healthcheck`
heading in the Findings-MD. If `--healthcheck-only`, that's the entire
output (no Phase 1, no Phase 2). The file lands at
`<findings_dir>/YYYY-MM-DD-healthcheck.md`.
