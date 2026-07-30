---
name: audit
description: >
  Run a security audit across one or more repositories. Checks tool availability,
  executes the project's `scripts/security-audit.sh` if present (otherwise falls
  back to running individual tools), parses JSON reports, and summarizes findings
  by severity. Use when asked to "run audit", "security scan", "check
  vulnerabilities", or "/we:audit".
---

# Security Audit

Run a comprehensive security audit across one or more repositories using
automated scanning tools.

---

## Workflow

```
1. Check tool availability
2. Run security-audit.sh (or individual tools)
3. Parse JSON reports
4. Present findings summary
5. Recommend manual review steps
```

---

## Phase 1 — Tool Availability

Probe for `semgrep`, `trivy`, `kubescape`, `gitleaks`, `bandit`. A missing tool is a **warning, not
a blocker** — note which scans were skipped and continue with what is installed.

All of them missing → stop and say so; there is nothing to report and a clean-looking summary from
zero scanners is worse than no summary. Point at the install docs (`pip install semgrep`, the Trivy
/ Kubescape / Gitleaks project pages).

## Phase 2 — Run Audit Script

If the project ships its own audit script, prefer it (it will know which tools
to invoke and where to write reports):

```bash
SCRIPT="scripts/security-audit.sh"
if [ -f "$SCRIPT" ]; then
  bash "$SCRIPT" --skip-history
fi
```

**If no project script is present:** run individual tools manually:
- `semgrep scan --config auto --json --output /tmp/semgrep.json .`
- `trivy fs --scanners vuln --format json --output /tmp/trivy.json .`
- `gitleaks detect --source . --report-format json --report-path /tmp/gitleaks.json --no-git`

## Phase 3 — Parse Reports

Read the JSON reports — from the project's report directory when a script wrote them, `/tmp`
otherwise — and count findings per severity. Where each tool keeps its severity:

| Tool | Severity field | Scale |
|---|---|---|
| Semgrep | `results[].extra.severity` | ERROR / WARNING / INFO |
| Trivy | `Results[].Vulnerabilities[].Severity` | CRITICAL / HIGH / MEDIUM / LOW |
| Kubescape | `results[].controls[].status` | failed / passed |
| Gitleaks | top-level array | one entry = one finding |
| Bandit | `results[].issue_severity` | HIGH / MEDIUM / LOW |

## Phase 4 — Present Summary

One table, tools as rows, severities as columns, totals per row. Then **list every CRITICAL and
HIGH individually** with its file path and description — a count tells the user there is a problem,
a path tells them where.

## Phase 5 — What the scanners cannot see

Automated scans find *classes* of bug, never *your* logic. Close the report by naming what still
owes a human pass:

- **Auth & access control** — row-level policies, token validation, role checks on the paths that
  matter
- **Abuse & billing** — race conditions on credit, webhook idempotency, rate limits on the
  expensive endpoints
- **Privacy** — PII in logs and payloads, data residency, retention and deletion paths
- **Secrets** — at-rest encryption, how CI and the cluster inject them
- **Infrastructure** — network policy, container hardening, transport security

If the project keeps a threat model, point at it here rather than repeating it.

---

## Options

| Flag | Effect |
|------|--------|
| `--quick` | Skip git history scan (faster) |
| `--full` | Include git history scan (slower, more thorough) |
| `--repo <name>` | Scan only one repo when running across a multi-repo workspace |
