---
name: doc-review
description: >
  Systematic documentation review — validates structure, frontmatter, detects
  duplicates, checks token efficiency. Use when reviewing documentation quality,
  validating rules setup, or when user mentions "doc-review", "documentation review".
---


# Documentation Reviewer

**Role:** Ensures documentation quality across the project.

---

## 4-Layer Knowledge System

| Layer | Location | When Loaded | Content |
|---|---|---|---|
| **CLAUDE.md** | Repo roots | Always | Vision, Quick-Ref, Links |
| **Rules** | `.claude/rules/` | Path-filtered | Technical patterns |
| **Skills** | `.claude/skills/` | On invocation | Methodology |
| **docs/** | `docs/` | Manual/Search | Human-readable details |

---

## Usage

```bash
/we:doc-review                # Full review
/we:doc-review rules          # Rules only (frontmatter, paths, size)
/we:doc-review [file.md]      # Single file
```

---

## Checks

### Universal (All Documents)

| Check | Severity |
|---|---|
| Broken links | ISSUE |
| Duplicate content (>50% overlap) | WARNING |
| Stale (>3 months without update) | WARNING |
| Missing metadata (version, date) | INFO |
| Over 500 lines | INFO |

### CLAUDE.md Specific

- Hierarchy compliance (root → workspace → repo → layer)
- No redundancy with parent CLAUDE.md
- Commands in code blocks

### Rules Specific

```yaml
# Path-filtered rule (loads when editing matching files):
---
paths: src/**/*.py
---

# Always-loaded rule (no paths):
---
---
```

| Check | Severity |
|---|---|
| Frontmatter syntax (opening + closing `---`) | ISSUE |
| Path pattern resolves to actual files | ISSUE |
| Size within limits (50-400 lines) | WARNING |
| No duplicates with CLAUDE.md | WARNING |

### Skill Specific

| Check | Severity |
|---|---|
| YAML frontmatter (name, description) | ISSUE |
| name matches directory | ISSUE |
| Description includes trigger words | WARNING |
| Instructions are step-by-step | WARNING |

---

## Deduplication Rules

| Duplicate Type | Resolution |
|---|---|
| Rule ↔ Rule | Keep one, delete other |
| Rule ↔ CLAUDE.md | Keep in Rule, reference from CLAUDE.md |
| Rule ↔ Skill | Keep in Rule, Skill references |
| Skill ↔ Skill | Extract to shared location |

---

## Token Efficiency

**Rules load on EVERY relevant file edit.** Keep them:
- **Focused:** One topic per rule
- **Concise:** Tables > long paragraphs
- **Practical:** Code examples > theory
- **Deduplicated:** Reference, don't copy

---

## Output Format

```markdown
## Doc-Review Report

**Files Reviewed:** X
**Issues Found:** X (Y Blockers, Z Warnings)

### BLOCKERS
| File | Issue | Fix |
|------|-------|-----|

### WARNINGS
| File | Issue | Suggestion |
|------|-------|------------|

### TOKEN ANALYSIS
| Category | Files | Lines | Est. Tokens |
|----------|-------|-------|-------------|
```

---

## Placement Decision Tree

```
Is this for Claude Code?
├── NO → docs/ (human reference)
└── YES → What type?
    ├── Vision/Fundamentals → CLAUDE.md
    ├── Git/CI/Story workflows → rules/workflows/
    ├── Stack-specific patterns → rules/stacks/ (with paths:)
    ├── Quality/Testing → rules/quality/ (with paths:)
    ├── Methodology for ONE skill → Keep in Skill
    └── Overview only → CLAUDE.md
```
