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

Check which tools are installed. Missing tools are warnings, not blockers.

```bash
for tool in semgrep trivy kubescape gitleaks; do
  if command -v "$tool" &>/dev/null; then
    echo "OK: $tool ($($tool --version 2>/dev/null | head -1))"
  else
    echo "MISSING: $tool — install to enable scanning"
  fi
done
```

**If all tools missing:** Stop and tell the user to install tools first. Recommend:
```bash
pip3 install semgrep
# Trivy: https://aquasecurity.github.io/trivy/
# Kubescape: curl -s https://raw.githubusercontent.com/kubescape/kubescape/master/install.sh | bash
# Gitleaks: https://github.com/gitleaks/gitleaks
```

**If some tools missing:** Continue with available tools, note which scans were skipped.

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

Read JSON reports (from the project's report directory if a script wrote them,
otherwise from `/tmp/`) and summarize:

```python
import json, glob

# Adjust the directory to wherever the script (or your manual run) wrote reports.
report_dir = "docs/security/reports"  # or "/tmp"
for tool in ["semgrep", "trivy", "kubescape", "gitleaks", "bandit"]:
    reports = glob.glob(f"{report_dir}/{tool}/*.json") + glob.glob(f"{report_dir}/{tool}.json")
    # Parse and count findings by severity
```

**Semgrep:** `results[].extra.severity` → ERROR/WARNING/INFO
**Trivy:** `Results[].Vulnerabilities[].Severity` → CRITICAL/HIGH/MEDIUM/LOW
**Kubescape:** `results[].controls[].status` → failed/passed
**Gitleaks:** Top-level array, each item = one finding
**Bandit:** `results[].issue_severity` → HIGH/MEDIUM/LOW

## Phase 4 — Present Summary

Format findings as a table:

```
| Tool     | CRITICAL | HIGH | MEDIUM | LOW | Total |
|----------|----------|------|--------|-----|-------|
| Semgrep  |        0 |    2 |      5 |   3 |    10 |
| Trivy    |        1 |    4 |      8 |   2 |    15 |
| ...      |          |      |        |     |       |
```

For CRITICAL/HIGH findings, list each one with file path and description.

## Phase 5 — Manual Review Reminder

After automated scans, remind about checks that can't be automated:

- **Auth & Access Control:** RLS policies, JWT validation, role-based access
- **Billing & Abuse:** Credit race conditions, webhook idempotency, rate limiting
- **Data Privacy (GDPR):** PII exposure, data residency, retention policies
- **Secrets:** Encryption-at-rest, K8s/CI secret management
- **Infrastructure:** Network policies, container security, transport security

If the project keeps a threat-model document (e.g. `docs/security/AUDIT-PROCEDURE.md`),
reference it here.

---

## Options

| Flag | Effect |
|------|--------|
| `--quick` | Skip git history scan (faster) |
| `--full` | Include git history scan (slower, more thorough) |
| `--repo <name>` | Scan only one repo when running across a multi-repo workspace |
