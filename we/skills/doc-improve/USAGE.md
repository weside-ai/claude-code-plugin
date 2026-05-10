---
name: doc-improve-usage
description: Real-world use cases + 28-file sweep case-study for /we:doc-improve. Read after SKILL.md — case-book complement, not duplicate.
---

# /we:doc-improve — Real-World Use Cases

How this skill gets used in practice, with three illustrative runs from a
large internal Python+TypeScript monorepo. Read after [SKILL.md](SKILL.md) —
this is the case-book.

## When to reach for it

The skill answers one question: **does the file still tell the truth, and
does it earn the bytes a reader spends on it?** Reach for it when:

- A doc was written months ago and the codebase has moved.
- A sibling rule co-loads with this one and you suspect overlap.
- An always-loaded rule (`core/`, `workflows/`) has grown and no one is sure
  which sections still earn their always-loaded slot.
- Before a release, as a sanity pass on the rules or CLAUDE.md.
- After someone says "the agent kept doing X — the rule says don't" and you
  want to confirm the rule actually says don't.

## When NOT to reach for it

- "Where should this new pattern go?" → `/we:docs` (doc-architect agent).
- "Audit the whole `docs/` tree." → `/we:docs` again — it's the orchestrator.
- "Fix this typo." → just fix the typo; don't dispatch a substantive review.
- "Generate frontmatter / fix broken links." → that's a linter job, not this.

---

## Use case 1: single-file pre-merge sanity check

You touched `core/architecture-boot.md` in a story and want to make sure the
file is still tight before merging.

```text
/we:doc-improve .claude/rules/core/architecture-boot.md
```

The skill:

- Reads `quality/doc-standards.md` + `references/rules.md` to ground itself.
- Verifies every claim (code structure, primitive index, fixed-cardinality
  tables) against the live code (e.g. backend modules, architecture docs).
- Fires Pillar 5d ("always-loaded fit") because the rule has no `paths:`
  field. Verdict line is mandatory: `Always-loaded fit: clean | mismatch — X%
  subsystem-specific`.
- Returns a structured report with severity-tagged findings + concrete diffs.

**Real outcome:** the always-loaded rule had a backend-only code-structure
block that was ~70% irrelevant for frontend edits — present on every
frontend session too, which it shouldn't be. Pillar 5d fired with a
"mismatch" verdict. The trim shipped as a small commit and saved roughly
a dozen lines per session.

---

## Use case 2: full-tree sweep

You suspect drift across many rules and want to triage. Worktree first, then
run the skill against every rule + the repo CLAUDE.md.

```bash
git worktree add .worktrees/doc-improve-sweep -b chore/doc-improve-rules-sweep
```

```text
/we:doc-improve ".claude/rules/**/*.md" CLAUDE.md
```

The skill batches the work and produces:

- A per-batch report (e.g. `B1-core.md`, `B3a-stacks-backend.md`).
- A master aggregate (`MASTER-AGGREGATE.md`) with severity totals,
  cross-cluster drifts ("the same fix lives in 5 files"), and a recommended
  apply order ranked by leverage (always-loaded reach × drift severity ×
  cross-file payoff).

**Real outcome (one merged sweep PR):** 28 files reviewed, 110 findings
(7 BLOCKER · 49 MAJOR · 41 MINOR · 13 NIT). Cross-cluster patterns
surfaced five distinct dedup themes — typical shapes the master aggregate
will produce:

| Theme shape | Files | Outcome |
|---|---|---|
| Multi-file narration of one CLI command (workflow described in 5 places) | 5 | Pick canonical home in the matching stack rule; CLAUDE.md collapses to a 3-line pointer |
| Triple-coverage of one operational subcommand | 3 | Canonical home → deployment rule; siblings keep one-line pointer |
| Audit-log conventions duplicated across two billing rules | 2 | Canonical home → the writer-side rule that owns the helper |
| UI prop fabricated in two rules, real prop is different | 2 | Both rules updated to match the live API; one source of truth |
| Naming inconsistency for two adjacent React-Query bridges | 2 | Public vs internal name disambiguated in both rules |

Total: 10 commits over 28 files. Always-loaded surface ~170 lines slimmer
per session.

---

## Use case 3: drift triage on a single drifting rule

You merged a feature flag, and a rule that explained the old behaviour is
now wrong in subtle ways. You want a substantive read.

```text
/we:doc-improve .claude/rules/stacks/billing-metering.md
```

The skill flags exactly the drifted claims, with line-level diffs:

- A `primitive.py:172-176` line citation went stale (the block moved).
  → Replace with a block-name reference (line numbers drift, names don't).
- An audit-log block fully overlaps a sibling rule's same-named heading.
  → Pick canonical home (writer-side, where the helper that emits the
  audit-log entry actually lives); collapse the duplicate to a one-line
  pointer.

Report severity tags tell you which findings block a merge (BLOCKER, MAJOR)
vs. which are polish (MINOR, NIT).

---

## What the skill checks

Quick reference; the full machinery is in [SKILL.md](SKILL.md).

**Universal pillars** (every doc):

1. **1a — API completeness.** Listings (class methods, CLI commands, config
   keys) match the live code. Verified by grep.
2. **1b — Invariants.** Claimed rules ("only X imports Y") survive a grep
   against the codebase.
3. **1c — Cross-claim consistency.** Two sentences in the same doc, or two
   sibling docs, don't contradict each other.
4. **2 — Reader informativeness.** A reader who lands here gets useful
   guidance in the first 30 seconds.
5. **3 — Redundancy.** No "this is also explained over there" without a
   single canonical home.
6. **4 — Currency.** Stale plans, "Phase 2" markers that silently shipped,
   open TODOs that closed.

**Rules-mode adds Pillar 5** ([references/rules.md](references/rules.md)):

| Sub-check | What |
|---|---|
| 5a — Token budget | Path-filtered cap (~500 lines); always-loaded rules earn every byte |
| 5b — Paths-frontmatter | Field name (`paths:`, not `globs:`), no brace-expansion, no string concatenation |
| 5c — Trigger overlap | Sibling rules with identical `paths:` shouldn't restate each other |
| 5d — Always-loaded fit | Universal-titled rules whose body is subsystem-specific; mandatory verdict line |
| 5e — CLAUDE.md duplication | A rule that re-states what's in `CLAUDE.md` is a token tax |

---

## Output format

The skill always returns:

- One line summary per file (verdict: KEEP / TIGHTEN / SPLIT / REWRITE).
- Pillar-by-pillar checklist outcome (✓ / finding-id).
- For each finding: severity tag, pillar, where, what, why, proposed diff.
- "What stays" — explicit list of sections you should NOT touch.
- Effort estimate.
- Downstream impact (other files that reference what's changing).

Severity tags:

- **BLOCKER** — actively misleads, mis-teaches, or breaks if followed.
- **MAJOR** — drift or redundancy that costs reader time / accuracy.
- **MINOR** — small accuracy or clarity improvement.
- **NIT** — cosmetic, defensible to skip.

---

## Tips

- **Run in a worktree** if the file count is high. Even though the skill
  proposes-only, you'll be cycling diffs through edits + commits.
- **Apply in clusters** — the master aggregate's "recommended apply order"
  groups findings by leverage so you don't ping-pong across files.
- **Keep the per-file reports** (they're written to `/tmp/doc-improve-runs/`
  by default). Useful for the PR body and for follow-up reviews.
- **Trust the verifications.** The skill verified each claim against live
  code; if a finding's diff doesn't apply cleanly because the file moved,
  adapt the diff — don't skip the finding.
- **Don't re-run the skill on a file you just edited.** Edit, commit, move
  on. The skill itself is a one-shot review, not a watch loop.
