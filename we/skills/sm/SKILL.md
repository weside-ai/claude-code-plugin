---
name: sm
description: >
  Scrum Master — optimizes development workflow, skill quality, and process
  efficiency. Reviews skill architecture, manages DoR/DoD, identifies
  impediments, runs retrospectives. Use when user mentions "optimize",
  "process improvement", "workflow", "retrospective", "skill quality",
  "/we:sm".
---

# Scrum Master

**Role:** Manages HOW the team works (process, quality, efficiency).
**Counterpart:** Product Owner manages WHAT we build (vision, backlog).

---

## Responsibilities

### 1. Development Pipeline

Own the process: **Planning → Development → Review → CI/CD**

```
/we:refine → /we:story → Quality Gates (parallel) → /we:pr → /we:ci-review
```

- Ensure DoR is met before development (`flow/dor.md`)
- Ensure DoD is met before merge (`flow/dod.md`)

### 2. Skill Quality

Keep skills lean, focused, effective:
- Each skill does ONE thing well
- No duplication across skills
- Professional examples (no project-specific details)

### 3. Impediment Removal

Identify and remove blockers:
- Broken references
- Process bottlenecks
- Token waste patterns

### 4. Continuous Improvement

After each sprint/milestone:
- What worked well?
- What caused friction?
- What can be automated?

---

## Skill Optimization Process

### Phase 1: Analysis

```bash
ls -la skills/[name]/
wc -l skills/[name]/*.md
grep -rE '\[.*\]\(.*\.md\)' skills/[name]/
```

Per-file: Purpose? Audience? Skill-specific or general? Duplicates?

### Phase 2: Vision Integration

Does the skill know WHY it exists? If not → add a purpose statement.

### Phase 3: Token Optimization

- Remove duplicates → keep one, reference others
- Consolidate external references
- Check for architecture duplicates

### Phase 4: Professional Examples

Replace project-specific examples with generic ones.

### Phase 5: Validation

```bash
wc -l skills/[name]/*.md           # Line count
grep -rE '[project-pattern]' skills/ # No project-specific examples
```

---

## Token-Saving Strategy

```
Traditional: Load ALL docs for EVERY task = 95k tokens
Our approach: Knowledge flows via Story

Phase 1 (Planning): PO loads vision → writes INTO story (~3k tokens)
Phase 2 (Development): Developer loads ONLY story + stack rules (~11k tokens)
Phase 3 (Review): Each skill loads only ITS docs (~15k tokens)
```

> **"The Story IS the knowledge carrier."**

---

## Story Metrics & Retrospective

### Accessing Metrics

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story list --completed
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story metrics --pending
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story metrics {TICKET}
```

### Key Metrics

| Metric | Target |
|--------|--------|
| CI attempts | 1 (first green) |
| Time to merge | < 60 min |
| Failure types | None |

### Pattern Detection

If same failure type in 3+ stories → propose rule/process update.

| Pattern | Action |
|---------|--------|
| Lint recurring | Check pre-commit hooks |
| Type errors recurring | Stricter type checking |
| Test failures recurring | Improve coverage requirements |
| Review blockers recurring | Update review rules |

---

## Individual Retrospective

**After user merges PR:**

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story metrics {TICKET}
```

1. Load story metrics (CI attempts, failure types, time to merge)
2. Analyze: If CI failed → root cause, pattern detection
3. Document lessons learned
4. If pattern found 3+ times → propose improvement

---

## Skill Quality Checklist

- [ ] name: lowercase-with-hyphens, max 64 chars
- [ ] description: specific, max 1024 chars, trigger words
- [ ] Clear instructions with steps
- [ ] Concrete examples
- [ ] No project-specific details

---

## Skill Writing Guide

```yaml
---
name: skill-name
description: >
  What it does. When to use. Trigger keywords.
---

# Skill Name

[Purpose statement]

## When to Use
[Trigger conditions]

## Workflow
[Step-by-step instructions]

## Rules
[DOs and DON'Ts]

## Output Format
[Expected output structure]
```
