# Development Process

**The /we:* pipeline — from idea to merged PR.**

---

## The Big Picture

```
Idea → /we:refine → /we:story → User merges → Done
         (manual)    (autonomous)   (manual)
```

**Three phases, clear responsibilities:**

| Phase | Who | What | Command |
|-------|-----|------|---------|
| **Planning** | User + Claude (interactive) | Story + Plan | `/we:refine` |
| **Development** | Claude (autonomous) | Code → Review → Test → PR → CI | `/we:story` |
| **Delivery** | User (manual) | Review PR, merge, close ticket | GitHub / Ticketing |

---

## Phase 1: Planning (/we:refine)

**Interactive.** Claude asks questions, user makes decisions.

```
User describes feature
  ↓
Claude asks clarifying questions
  ↓
Claude creates MINIMAL ticket + DETAILED plan
  ↓
User approves plan (EnterPlanMode)
  ↓
SQLite: phase=refined
```

**Output:**
- Ticket: "As X I want Y so that Z" + link to plan
- Plan: `docs/plans/{TICKET}-plan.md` with ACs, phases, tests, security review

**DoR must be met** before development starts (`flow/dor.md`).

---

## Phase 2: Development (/we:story)

**Autonomous.** Claude runs the entire pipeline without stopping.

```
/we:story {TICKET}
  │
  ├── Step 0: Check for Resume (interrupted session?)
  ├── Step 1: Load Story + Plan, Reality Check, move ticket to "In Progress"
  │
  ├── Step 2: /we:develop
  │     ├── Create feature branch
  │     ├── Implement phase by phase
  │     ├── Auto-fix + local tests
  │     └── Checkpoint: implementation_complete
  │
  ├── Step 3: AC Verification Gate (BLOCKING)
  │     └── Every AC verified with file/test evidence
  │
  ├── Step 4: Simplify
  │
  ├── Step 5: Quality Gates (PARALLEL)
  │     ├── /we:review  → code-reviewer agent
  │     ├── /we:static  → static-analyzer agent
  │     ├── /we:test    → test-runner agent
  │     └── CodeRabbit   (if available)
  │
  ├── Step 6: /we:docs (auto-update documentation)
  │
  ├── Step 7: /we:pr
  │     └── Prerequisite check: review + static + test all passed?
  │
  ├── Step 8: /we:ci-review
  │     └── Collect → Triage → Batch-fix → Resolve → Push (max 3 cycles)
  │
  └── Step 9: Ticket → "In Review"
```

### Checkpoint Phases

Each step writes a checkpoint to SQLite. If interrupted, `/we:story` resumes from the last checkpoint.

| Phase | Written By | After |
|---|---|---|
| `refined` | /we:refine | Story + Plan created |
| `git_prepared` | /we:develop | Branch created |
| `implementation_complete` | /we:develop | Code committed |
| `ac_verified` | /we:story | All ACs verified |
| `simplified` | /we:story | Code simplified |
| `docs_updated` | /we:docs | Documentation updated |
| `review_passed` | /we:review | Code review passed |
| `static_analysis_passed` | /we:static | Lint/format/types passed |
| `test_passed` | /we:test | Tests + coverage passed |
| `pr_created` | /we:pr | PR on GitHub |
| `ci_passed` | /we:story | CI/Reviews green |

### Circuit Breaker

After 3 failures in the same phase → pipeline stops and asks the user. Prevents infinite loops.

### Quality Gates (Parallel)

All 4 gates run simultaneously as background agents. This saves ~40% time compared to sequential execution.

---

## Phase 3: Delivery (User)

Claude outputs a PR with:
- All ACs implemented and verified
- Code review passed
- Tests passing with coverage
- CI green (or reviews green, CI pending)
- Ticket in "In Review"

**User does:**
1. Review PR on GitHub
2. Merge
3. Move ticket to "Done"

**Claude NEVER merges PRs or moves tickets to "Done."**

---

## Robustness Features

| Feature | How | Benefit |
|---------|-----|---------|
| **Checkpoints** | SQLite saves progress after each phase | Resume after interruption |
| **Circuit Breaker** | 3 failures → stop | No infinite loops |
| **CI-Fix Loop** | Collect + batch-fix + push (max 3 cycles) | One commit per fix round |
| **Reality Check** | Compare plan creation date vs. recent git changes | Detect stale plans |
| **Prerequisite Gates** | PR requires 3 checkpoints | No PR without quality |

---

## Skill & Agent Map

### Skills (user-invokable)

| Skill | Phase | Purpose |
|-------|-------|---------|
| `/we:setup` | Onboarding | Detect stack, ticketing, optional vision |
| `/we:refine` | Planning | Create story + plan (interactive) |
| `/we:story` | Development | Orchestrate full pipeline (autonomous) |
| `/we:develop` | Development | Implement code (called by story or standalone) |
| `/we:ci-review` | Development | Collect + fix CI/review findings |
| `/we:sm` | Process | Optimize workflow, retrospectives |
| `/we:arch` | Ad-hoc | Architecture guidance, ADRs |
| `/we:doc-review` | Ad-hoc | Documentation structure review |
| `/we:doc-check` | Ad-hoc | Documentation content consistency |
| `/we:docs` | Development | Auto-update documentation (called by story Step 6) |
| `/we:find-dead-code` | Ad-hoc | Remove dead code from Python backends |
| `/we:materialize` | Session | Load weside Companion (optional) |

### Agents (background, called by skills)

| Agent | Called By | Purpose |
|-------|----------|---------|
| `code-reviewer` | /we:story Step 5 | Diff-based review, AC alignment |
| `static-analyzer` | /we:story Step 5 | Lint, format, types |
| `test-runner` | /we:story Step 5 | Tests + coverage |
| `pr-creator` | /we:story Step 7 | PR with prerequisite check |
| `doc-manager` | /we:story Step 6 | Auto-detect and update docs |

### Reference Documents (flow/)

| Document | Content |
|----------|---------|
| `dor.md` | Definition of Ready checklist |
| `dod.md` | Definition of Done checklist |
| `orchestration.md` | SQLite CLI reference |
| `epic-management.md` | Epic lifecycle and templates |
| `development-process.md` | Pipeline reference for agents |

---

## Token-Saving Strategy

```
Planning: PO loads vision + architecture → writes INTO story plan (~3k tokens)
Development: Developer loads ONLY story + plan (~5k tokens)
Review: Each agent loads ONLY its rules (~3k tokens each)
```

> **"The Story IS the knowledge carrier."**
> Planning skills read specialized docs ONCE, then write relevant knowledge INTO the plan.
> Development never needs those docs directly.

---

## Error Handling

| Situation | What happens |
|-----------|-------------|
| CI fails | /we:ci-review collects, triages, batch-fixes (max 3 cycles) |
| Review findings | Same: collect, fix, resolve threads, push |
| Circuit breaker opens | Pipeline stops, presents options to user |
| Plan is stale | Reality Check warns, user decides to proceed or re-refine |
| Checkpoint missing | PR creator blocks until quality gates pass |
| Interrupted session | /we:story detects and offers resume |

---

## Quick Reference

```bash
# Full pipeline
/we:refine "Feature description"    # Create story + plan
/we:story PROJ-1                     # Autonomous: develop → review → PR → CI

# Individual steps
/we:develop                          # Implement code
/we:static                           # Lint/format/types
/we:test                             # Run tests
/we:review                           # Code review
/we:pr                               # Create PR
/we:ci-review                        # Fix CI/review findings

# Process & quality
/we:sm                               # Process optimization
/we:arch                             # Architecture guidance
/we:docs                             # Auto-update documentation
/we:doc-review                       # Documentation review
/we:doc-check                        # Documentation consistency
/we:find-dead-code                   # Remove dead Python code

# Setup & companion
/we:setup                            # Project onboarding
/we:materialize                      # Load weside Companion
```
