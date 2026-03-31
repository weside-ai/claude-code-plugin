---
name: doc-check
description: >
  Documentation CONTENT consistency check. Finds outdated code references,
  contradictions, semantic duplicates. Reads docs thematically, not file-by-file.
  Use when user mentions "consistency", "outdated docs", "contradictions",
  "/we:doc-check".
---

# Doc-Check

You are an architect reading documentation. Your brain finds inconsistencies, not regex.

---

## Usage

```bash
/we:doc-check                # Full check (all themes)
/we:doc-check Memory         # Only one theme
/we:doc-check "Auth System"  # Quotes for multi-word themes
```

---

## The 3 Rules

### 1. Read Thematically

Not file-by-file. Collect ALL docs about ONE theme, read them together.

**Theme Discovery:** Scan the project's `docs/` directory and identify themes from folder structure and file names. Common themes: Architecture, Auth, Database, API, Deployment, Testing.

### 2. Write Findings IMMEDIATELY

Don't hold in memory. Write to findings file as you go:

```markdown
## [Theme]

- [ ] `file.md:123` — What's wrong
      Doc says: X
      Code has: Y

      CONFIDENCE: 95%
      DECISION: Doc is outdated
      FIX: Update code examples
```

### 3. Decide: Code vs Doc

- Code + ADR agree → Doc is wrong (CONFIDENCE 95%)
- Code contradicts ADR → Check timestamps, newer wins
- No ADR → Does code work? → Probably code is right (CONFIDENCE 70%)
- Everything contradicts → CONFIDENCE <50% → ASK USER

**Hierarchy:** Code (runs) > ADR (decided) > Docs (explains)

---

## Confidence Levels

| Level | Meaning | Action |
|---|---|---|
| **95-100%** | Code + ADR agree | Fix immediately |
| **70-94%** | Code works, no ADR | Probably doc outdated |
| **50-69%** | Conflicting signals | Note in findings, review later |
| **<50%** | Unclear | ASK USER immediately |

---

## Severity

| Tag | Meaning |
|---|---|
| **CRITICAL** | Following the doc causes errors |
| **HIGH** | Confusing, outdated |
| **MEDIUM** | Duplicate, redundant |

---

## Useful Checks

```bash
# Does the referenced path exist?
ls path/to/file.py

# Does the referenced function exist?
grep -n "def function_name" path/to/file.py

# When was it last changed?
git log -1 --format="%ai %s" path/to/file.py
```

---

## When Done

1. Review findings
2. Fix CRITICAL first
3. Group related fixes
4. One commit per theme

---

## Relationship to /we:doc-review

```
/we:doc-review = FORMAT (frontmatter, paths, size) — automatable
/we:doc-check  = CONTENT (contradictions, outdated) — needs judgment
```

Run `/we:doc-check` first (content), then `/we:doc-review` (format).
