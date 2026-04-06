---
name: audit
description: >
  Run security audit across weside repositories. Checks tool availability,
  executes scripts/security-audit.sh, parses JSON reports, and summarizes findings
  by severity. Use when asked to "run audit", "security scan", "check vulnerabilities",
  or "/we:audit".
---

# Security Audit

Run a comprehensive security audit across weside repositories using automated scanning tools.

---

## Workflow

```
1. Check tool availability
2. Run security-audit.sh
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

Execute the audit script from the weside-core repository:

```bash
# Find script (works from any weside repo)
SCRIPT="scripts/security-audit.sh"
if [ ! -f "$SCRIPT" ]; then
  SCRIPT="$HOME/weside/weside-core/scripts/security-audit.sh"
fi

# Run (--skip-history for faster results)
bash "$SCRIPT" --skip-history
```

**If script not found:** Run individual tools manually:
- `semgrep scan --config auto --json --output /tmp/semgrep.json .`
- `trivy fs --scanners vuln --format json --output /tmp/trivy.json .`
- `gitleaks detect --source . --report-format json --report-path /tmp/gitleaks.json --no-git`

## Phase 3 — Parse Reports

Read JSON reports from `docs/security/reports/` and summarize:

```python
import json, glob, os

report_dir = "docs/security/reports"
for tool in ["semgrep", "trivy", "kubescape", "gitleaks", "bandit"]:
    reports = glob.glob(f"{report_dir}/{tool}/*.json")
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
- **Data Privacy (DSGVO):** PII exposure, data residency, retention policies
- **Secrets:** Review SOPS encryption, K8s secret management
- **Infrastructure:** Network policies, container security, TURN server config

Reference: `docs/security/AUDIT-PROCEDURE.md` for the full 49-vector threat model.

---

## Options

| Flag | Effect |
|------|--------|
| `--quick` | Skip git history scan (faster) |
| `--full` | Include git history scan (slower, more thorough) |
| `--repo <name>` | Scan only one repo (core, cli, infra, landing, plugin) |
