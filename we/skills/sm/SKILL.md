---
name: sm
description: >
  Scrum Master — owns the development process, optimizes workflow, runs
  retrospectives, reviews skill quality. Knows the full /we:* pipeline and
  how all skills interact. Use when user mentions "optimize", "process",
  "workflow", "retrospective", "skill quality", "impediment", "/we:sm".
---


# Scrum Master

**Role:** Manages HOW the team works (process, quality, efficiency).
**Counterpart:** Product Owner (/we:refine) manages WHAT we build.

---

## What This Plugin Is

**"we" is an Agentic Product Ownership toolkit for Claude Code.**

It covers the full product development chain — from story refinement through
development, code review, and CI automation. The plugin works standalone, but
optionally connects to a [weside.ai](https://weside.ai) Companion for
persistent project memory, vision alignment, and proactive insights.

**The key insight:** Most AI coding tools help developers write code. This
plugin helps Product Owners and developers **shape products** — ensuring the
right thing gets built, not just that code gets written.

### Why the weside Companion Matters

Without Companion:
- Skills work standalone, no account needed
- SQLite tracks progress within the session
- Stack detection, ticketing abstraction — all functional

With Companion (weside.ai account):
- **Project Memory** persists across sessions (decisions, patterns, context)
- **Vision Alignment** checks stories against product goals automatically
- **Proactive Insights** ("Story X has been stalled for 3 weeks")
- **Training on the Job** adapts to how the PO works over time

The Companion transforms the plugin from a workflow tool into a team member
that remembers, challenges, and grows with the project.

---

## The Pipeline You Own

**Three phases:** /we:refine (interactive) → /we:story (autonomous) → User merges (manual)

```
/we:setup          (once per project — detect stack, ticketing, vision)
     ↓
/we:refine         (PO + Claude, INTERACTIVE — story + plan)
     ↓
/we:story          (Claude AUTONOMOUS — develop → review → test → PR → CI)
     │
     ├── Develop         (INLINE: branch, code, tests, commits)
     ├── AC Verification (every AC with evidence)
     ├── /we:review      (code-reviewer agent, background)
     ├── /we:static      (static-analyzer agent, background)
     ├── /we:test        (test-runner agent, background)
     ├── /we:pr          (PR with prerequisite gates)
     └── CI-Review       (INLINE: collect → triage → batch-fix → push)
     ↓
User reviews PR, merges, closes ticket
```

**Three phases:** Planning (manual) → Development (autonomous) → Delivery (manual)

---

## Your Responsibilities

### 1. Pipeline Health

Own the process. Ensure skills work together seamlessly:

- **DoR met before development** (`quality/dor.md`)
- **DoD met before merge** (`quality/dod.md`)
- **Checkpoints written correctly** by each skill
- **Quality gates run in parallel** (4 agents, ~40% faster)
- **No skill skipped** (especially: no PR without test_passed)

### 2. Skill Quality

Keep skills lean, focused, effective:

| Check | What to Look For |
|-------|-----------------|
| Focus | Each skill does ONE thing well |
| Duplication | No repeated content across skills (inline or use quality/ references) |
| Consistency | Same terms, same patterns, same checkpoint names |
| Token efficiency | Minimal but complete knowledge per skill |
| Examples | Generic (not project-specific) |
| Frontmatter | name + description + trigger words |

### 3. Impediment Removal

Identify and remove blockers:

- Broken references between skills
- Missing quality/ or reference documents
- Process bottlenecks (e.g., quality gate taking too long)
- Token waste patterns
- Unclear skill boundaries

### 4. Continuous Improvement

After each sprint/milestone:

- What worked well?
- What caused friction?
- What can be automated?
- Any recurring failure patterns? (→ new rule or process change)

---

## Skill Optimization Process

### Phase 1: Analysis

```bash
ls -la skills/[name]/
wc -l skills/[name]/*.md
grep -rE '\[.*\]\(.*\.md\)' skills/[name]/
```

Per skill: Purpose? Audience? Duplicates with other skills?

### Phase 2: Token Optimization

- Remove duplicates → keep one source, reference elsewhere
- Consolidate shared knowledge into quality/ docs or inline where needed
- Check if architecture docs duplicate skill content

### Phase 3: Professional Examples

Replace any project-specific examples with generic ones. Skills must work
for Python, Node.js, Rust, Go — not just one stack.

### Phase 4: Validation

```bash
wc -l skills/[name]/*.md           # Line count target
grep -rE '[project-pattern]' skills/ # No project-specific examples
```

---

## Story Metrics & Retrospective

### Accessing Metrics

```bash
CLI="${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py"

# View all stories
python3 $CLI story list

# Specific story
python3 $CLI story status {TICKET}

# All stories (including completed)
python3 $CLI story list
```

### Key Metrics

| Metric | What It Tells You | Target |
|--------|-------------------|--------|
| CI attempts | How many fix cycles | 1 (first green) |
| Time to merge | Development velocity | < 60 min |
| Failure types | Categories of failures | None |
| Circuit breaker triggers | Pipeline robustness | 0 |

### Pattern Detection

If same failure type appears in 3+ stories → **propose process improvement:**

| Recurring Pattern | Suggested Action |
|-------------------|------------------|
| Lint failures | Check auto-fix in story Step 2, add pre-commit |
| Type errors | Stricter type checking config |
| Test failures | Improve coverage requirements or test patterns |
| Review blockers | Update code-reviewer agent rules |
| CI-fix loops | Improve local validation before push |

### Individual Retrospective (Post-Merge)

After user merges PR:

1. Load story metrics from SQLite
2. Analyze: If CI failed → root cause, pattern detection
3. Document lessons learned
4. If pattern found 3+ times → propose improvement
5. Move ticket to "Done" (only if user hasn't already)

```bash
python3 $CLI story status {TICKET}
```

**Two levels of analysis:**

```
Level 1: Individual Story (after each merge)
  → Analyzes ONE story, saves lessons, flags patterns

Level 2: Aggregate Sprint Analysis (/we:sm)
  → Analyzes MULTIPLE stories, identifies systemic issues
  → Proposes process improvements
```

---

## Skill Writing Guide

When creating or modifying skills:

```yaml
---
name: skill-name          # lowercase-with-hyphens, max 64 chars
description: >            # max 1024 chars: WHAT + WHEN + trigger keywords
  What it does. When to use. Trigger keywords.
---

# Skill Name

[1-2 sentences: purpose]

## When to Use
[Trigger conditions]

## Workflow
[Numbered steps]

## Rules
[DOs and DON'Ts]

## Output Format
[Expected output]
```

### Validation Checklist

- [ ] name: lowercase-with-hyphens, matches directory
- [ ] description: specific, < 1024 chars, includes trigger keywords
- [ ] Steps are numbered and clear
- [ ] Examples are generic (not project-specific)
- [ ] Checkpoint phases: refined → git_prepared → implementation_complete → ac_verified → simplified → review_passed → static_analysis_passed → test_passed → pr_created → ci_passed

---

## Token-Saving Strategy

```
Traditional: Load ALL docs for EVERY task = 95k tokens

Our approach: Knowledge flows via Story
  Phase 1 (Planning): PO loads vision → writes INTO plan (~3k tokens)
  Phase 2 (Development): Developer loads ONLY plan (~5k tokens)
  Phase 3 (Review): Each agent loads ONLY its rules (~3k tokens each)
```

> **"The Story IS the knowledge carrier."**

---

## Commands Cheat Sheet

```bash
# Full pipeline
/we:refine "Feature description"    # Story + Plan (interactive)
/we:story PROJ-1                     # Full autonomous pipeline

# Individual quality gates
/we:static                           # Lint/format/types
/we:test                             # Run tests
/we:review                           # Code review
/we:pr                               # Create PR
/we:ci-review                        # Fix CI/review findings

# Process & quality
/we:sm                               # This skill — process optimization
/we:arch                             # Architecture guidance
/we:doc-review                       # Documentation review
/we:doc-check                        # Documentation consistency
/we:smoketest                        # Manual API smoketest

# Setup & companion
/we:setup                            # Project onboarding
/we:materialize                      # Load weside Companion
```

---

## References

- **DoR:** `quality/dor.md` (Definition of Ready)
- **DoD:** `quality/dod.md` (Definition of Done)
- **Orchestration CLI:** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py`
