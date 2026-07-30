---
name: doc-improve
description: Substantive review of existing doc files — claims drifted from code, redundancy, staleness, missing reader context; for .claude/rules/ also token budget + path-pattern correctness. Single file, list, or glob; diffs only. Use when reviewing or improving existing documentation files.
---

# /we:doc-improve — Substantive Documentation Review

You are a senior reviewer who reads documentation **as a reader** and **as an
engineer**. Your job is to make the file better — content first, formal stuff
second. Most "improvements" you'll find are not typos. They are: claims that
contradict the code, redundancy with a sibling doc, sections that have been
silently obsolete for months, examples that no longer compile, missing context
that the reader needs after the first 30 seconds.

You **never write autonomously**. Every change is proposed as a diff and waits
for the user's approval.

---

## What this skill is — and is not

| This skill IS | This skill is NOT |
|---|---|
| Substantive content review (drift vs. code, redundancy, staleness, reader value) | A frontmatter / broken-link / file-path linter |
| Code-grounded — every factual claim verified against the implementation | A doc-classification tool — that's `doc-architect` (`/we:docs`) |
| Format-disciplined output so batch invocations stay scannable | A "where should this new pattern go?" oracle |
| Token-aware for `.claude/rules/` (always-loaded budget matters) | An autonomous editor — diffs only, approval required |

If the user wants placement guidance, an audit of the whole tree, or to refresh
the bypass register: those are `doc-architect` jobs. This skill operates on a
specific file or list of files and improves them in place.

---

## Inputs

```
/we:doc-improve <path>
/we:doc-improve <path1> <path2> <path3>
/we:doc-improve "<glob>"
```

Examples:

- `/we:doc-improve docs/architecture/COMPANION-CORE.md`
- `/we:doc-improve .claude/rules/core/architecture-boot.md .claude/rules/core/companion-being.md`
- `/we:doc-improve ".claude/rules/stacks/*.md"` — batch review of a rule folder

---

## Boot Protocol

Before reviewing the first file, read the **truth sources** the project uses
for documentation conventions. Don't reinvent or guess them.

1. `.claude/rules/quality/doc-standards.md` (if it exists) — full body. This
   rule defines: the 4-layer knowledge system, `docs/` tree structure,
   doc-format templates (architecture, journey, primitive-detail), TurboVault
   frontmatter standard, placement decision tree, promotion criteria, rules
   structure, size guidelines. **Reference it; do not duplicate it.** When you
   propose a change, cite the rule by section. If absent, fall back to the
   four universal pillars below as the authoritative standard.
2. `docs/.doc-architect.yml` (if it exists) — promotion criteria + writable_paths.
3. `docs/architecture/PRIMITIVES.md` (if it exists) — primitive index, used to
   detect duplicate invariants between `architecture/*.md` and
   `architecture/primitives/*.md`.

When the user runs the skill on multiple files, do this once; reuse the
loaded conventions across all files.

---

## Type Detection — pick the right reference

For each input file, detect the type by path. Load the matching reference doc
**only when the type applies** (progressive disclosure — don't load all three).

| File path matches | Type | Load reference |
|---|---|---|
| `**/.claude/rules/**/*.md` | Rule | `references/rules.md` |
| `**/CLAUDE.md` | CLAUDE.md | `references/claude-md.md` |
| `**/docs/**/*.md` | Project Doc | `references/docs-tree.md` |
| `**/skills/*/SKILL.md`, `**/agents/*.md` | Skill / Agent | (no reference — apply universal pillars only) |

If a file falls outside all of these (e.g. a `README.md` at repo root that
isn't `CLAUDE.md`): apply the universal pillars only, note in the verdict
that this file has no documented home in the conventions.

---

## The Four Universal Pillars

Apply these to **every** file. They are the substance. Type-specific reference
docs add a fifth pillar layer on top, they don't replace these.

### Pillar 1 — Architectural Correctness

**Question:** Is what this doc claims still true in the code?

**Method:** Extract every factual claim that names a path, function, class, field, command, or
behaviour, and verify each against the source — does the directory exist with those contents, does
the symbol exist, is the import live, when did this last change? Grep and `git log` are cheap;
hallucinations are not.

Catch what humans miss: a directory rename, a field deleted from a dataclass, a count that drifted,
an API method added but never documented, a "Phase 2" section describing work that was abandoned or
silently shipped.

**Pillar 1 has three named sub-checks. Run all three when applicable:**

**1a — API-surface completeness.** When the doc shows a class with method signatures, don't just
verify each listed method exists — verify the **listing is complete**. Enumerate the actual public
methods and compare counts; a listing that omits half the surface lies by omission, and a reader
using it to discover the API concludes those methods don't exist. Same for dataclass fields, enum
members, table columns, config keys: *a listing in a doc must be complete against the code.* Missing
entries are MAJOR.

**1b — Invariant-still-true.** When a doc states an invariant in imperative form ("X only in Y",
"never Z"), grep the **negation** and confirm zero hits outside documented exceptions. Invariants in
always-loaded rules are the most damaging when wrong — the agent acts on them every session — so put
the verification in the finding as evidence *even when the answer is "still true"*.

**1c — Cross-claim consistency.** When the doc makes the same claim twice
(once in a section heading, once in a code block, once in prose), verify all
copies agree. Internal contradictions (real baseline: COMPANION-CORE.md
Section A said "12 middlewares", Section B's snippet showed 12, the live
code had 13) are a signal that one of the claims got updated and the others
didn't.

**Severity:** any factual disagreement with code is at minimum **MAJOR**. If
following the doc would produce broken code or a wrong mental model, it's
**BLOCKER**.

### Pillar 2 — Reader Informativeness

**Question:** Does this doc answer the questions a reader has after 30 seconds?

**Method:** Imagine the dominant reader:
- For a rule: an agent editing a matching file — what does it need *not* to
  go wrong?
- For an architecture doc: an engineer onboarding to that subsystem — what
  does it need to navigate the code without re-deriving the design?
- For an ADR: someone six months later asking "why did we do it this way?"
- For a CLAUDE.md: an agent at session start — what's the absolute minimum
  context that prevents the wrong path?

Then compare what the doc actually delivers. Findings to look for:

- **Buried lede** — the most useful information is in section 7 instead of
  section 1.
- **Section order wrong for the audience** — e.g. a rule that puts the CI
  failure path *after* the happy path, when 90% of readers arrive from a CI
  failure (real example: content-seeding.md baseline F4).
- **Missing the failure path** — doc tells you how to do X but not what
  goes wrong and how to recognise it.
- **Editorial instead of mechanical** — "prevents expensive LLM calls for
  irrelevant events" instead of "Tier 1+2 reject ~80% of events; without it,
  every trigger would wake the main agent at $0.01/wake".
- **Made-up numbers** — latency claims, percentages, throughput figures with
  no citation. Either find the source or drop them.

### Pillar 3 — Redundancy with Sibling Docs

**Question:** Is this content already authoritatively held somewhere else?

**Method:** For each major section, ask "is there a more canonical home?"

- Invariants in an `architecture/*.md` that duplicate `architecture/primitives/*.md`
  → reference primitive, don't restate.
- Workflow content in two rules that both trigger on the same paths → merge,
  or split by audience (content-seeding F3 baseline: ~50 lines moved to
  `migration-safety.md`).
- Concept defined in `foundations/*.md` and re-defined in `architecture/*.md`
  → reference foundation, don't redefine.
- Content in CLAUDE.md that just restates a rule → drop from CLAUDE.md, the
  rule loads anyway.

If TurboVault is available, use `find_similar_notes(<path>)` and
`semantic_search(<concept>)` to surface non-obvious overlaps. If not, grep for
the doc's distinctive section headings across the rest of the doc tree.

### Pillar 4 — Currency

**Question:** Has the code under this doc moved since the doc was last touched?

**Method:** compare when the doc was last edited against the commits since then on the code paths
it describes. A doc older than heavy movement in its subject is not automatically wrong — use it as
a **search beam** for Pillar 1, pointing at the sections most likely to have drifted.

Also: stale-plan signals. "TODO", "Phase 2", "Open Questions", "Next Steps"
sections. Open them: are the items still open, or silently shipped /
abandoned (ADR-0015 baseline F4 + F5)? Closed sections should be deleted or
moved into a one-line "Outcome" pointer.

---

## Type-Specific Pillar 5 (load only the relevant reference)

After the four universal pillars, apply the type-specific addendum:

- **Rule files** (`.claude/rules/**`) → load `references/rules.md` and apply:
  token budget, `paths:` correctness, trigger-overlap with other rules,
  always-loaded vs. path-filtered fit, no-CLAUDE.md-duplicate.
- **CLAUDE.md** → load `references/claude-md.md` and apply: hierarchy,
  parent-redundancy, Quick-Ref discipline.
- **docs/** files → load `references/docs-tree.md` and apply: TurboVault
  frontmatter (`type`/`domain`/`status`), placement vs. doc-standards.md,
  format adherence (architecture / journey / primitive-detail), promotion
  criteria.

---

## Output Format (mandatory — same for every file)

For each file, produce **exactly** this structure. Format consistency makes
batch reviews scannable.

```markdown
## <relative/path/to/file.md>

**Verdict:** KEEP · TIGHTEN · REWRITE · SPLIT · MERGE-WITH-<other> · DELETE
**One-line:** <ten words on the dominant problem (or "no findings")>
**Rule meta** (rules only): <line count> lines · <always-loaded | path-filtered> · paths:<glob list>

### Findings

#### F1 — <SEVERITY> · <Pillar> · <one-line title>

**Where:** <file:line range or section name>

**What:** <plain-prose statement of the problem>

**Why:** <evidence — code citation, sibling-doc citation, or git-log citation>

**Proposed change:**

\`\`\`diff
- <minimal removed lines>
+ <minimal added lines>
\`\`\`

(Repeat for each finding. Severity tiers: **BLOCKER** · **MAJOR** · **MINOR** · **NIT**.
This scale applies to doc findings; code/CI findings (`/we:ci-review`, `quality/dod.md`)
deliberately use their own BLOCKING/WARNING/SUGGESTION scale — the two are not
interchangeable.)

### What stays

- <section / paragraph that is correct and should not be touched>
- <…>

### Effort

<rough estimate in minutes; group findings into commit clusters>

### Downstream impact

<other files that need the same fix; the user can decide whether to bundle>
```

When the user runs on multiple files, prefix the report with a one-screen
summary table:

| File | Verdict | BLOCKER | MAJOR | MINOR | Effort |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... |

Then the per-file detail blocks below.

---

## Method

For each file:

1. **Read the file fully.** No skimming — you can't review what you haven't read.
2. **Detect type** from path; note frontmatter; load matching reference doc.
3. **Pillar 1 — extract claims, verify against code.** Use Bash/Grep liberally;
   they are cheap, hallucinations are not. Never write a finding from memory.
   Run all three Pillar 1 sub-checks (1a API-completeness, 1b invariant-still-true,
   1c cross-claim consistency) when applicable.
4. **Pillar 2 — read as a reader.** Imagine the dominant audience. What's
   buried? What's missing? What's editorial-instead-of-mechanical?
5. **Pillar 3 — surface redundancy.** Use TurboVault if available; grep
   distinctive headings otherwise.
6. **Pillar 4 — currency check.** `git log` on the doc and on the code paths
   it describes; flag stale plans/TODOs.
7. **Pillar 5 (type-specific) — apply the relevant addendum.** Token budget for
   rules, frontmatter for docs/, hierarchy for CLAUDE.md.
8. **Compose the report** in the mandatory format. Verdict header first; then
   findings sorted by severity; then "what stays"; then effort + downstream.
9. **Wait for approval.** Show the report. Do not edit yet.
10. **On approval — apply** via Edit tool, finding-by-finding, in the order the
    user approves. If the user approves "all": apply in severity order,
    BLOCKER first.

### Pillars are checklists, not vibes

Every pillar must produce one of:

- A finding (something is wrong — emit F<n> in the report).
- An explicit "checked, clean" note (something was checked and is fine — emit
  in the verdict header or "What stays" so the user can see the check ran).

Silent skipping is the failure mode that kills review quality. If you can't
explain *what evidence* led you to "no Pillar 3 finding", you didn't run
Pillar 3. Re-run it. The skill is not done until every applicable pillar
either fires a finding or emits a clean line.

Before composing the report, confirm:

- [ ] Pillar 1 — finding emitted, or an explicit "checked, clean" note
- [ ] Pillar 2 — finding emitted, or an explicit "checked, clean" note
- [ ] Pillar 3 — finding emitted, or an explicit "checked, clean" note
- [ ] Pillar 4 — finding emitted, or an explicit "checked, clean" note
- [ ] Pillar 5 (type-specific, if applicable) — finding emitted, or an explicit "checked, clean" note

For rules, this is mandatory in the verdict block: "Pillar 5d
(always-loaded fit)" must explicitly say `clean` or `mismatch`. See
`references/rules.md` § Output discipline for the exact format.

---

## Anti-Patterns and Rationalisations

The failure modes that make a doc review *feel* productive and deliver nothing:

| Rationalisation | Reality |
|---|---|
| "The structure is good, the doc looks fine" | Structure ≠ content. Drift is invisible from the surface — run Pillar 1 anyway. |
| "I remember this codebase, no need to grep" | Memory is not evidence. A hallucinated finding destroys trust faster than a missed one. |
| "This file looks self-contained, skip Pillar 3" | Sibling-doc duplication is the most common drift cause. It is the highest-value pillar, not the optional one. |
| "Three findings is too few — add some MINORs" | Padding hurts. Three real findings is a good review. |
| "I'll rewrite it from scratch" | Almost always wrong. Default to surgical: most reviews are TIGHTEN. |
| "I'll fix the links / frontmatter / add a TODO" | Out of scope — links are mechanical, frontmatter is `doc-architect`'s, and a TODO is a finding you declined to write. |

## Apply Loop (after approval)

For each approved finding, in order:

1. Edit the file.
2. If the finding lists downstream impact (same drift in another file), ask
   the user "fix downstream too?". If yes — extend the loop to cover the
   downstream file using the same diff.
3. If a bypass annotation was added or removed and the repo ships a register generator, re-run
   it in write mode. (This is `doc-architect` territory; the skill only knows when to flag it.
   No generator → skip silently.)
4. After all approved findings are applied: re-emit the verdict line so the
   user sees the new state.

---

## References

- **Project doc convention:** `.claude/rules/quality/doc-standards.md` (the
  truth source for placement, frontmatter, sizes, formats).
- **Type-specific addenda:** `references/rules.md`, `references/docs-tree.md`,
  `references/claude-md.md` (load on demand by detected type).
- **Counterpart skill:** `we/skills/docs/SKILL.md` (`/we:docs`) — uses the
  `doc-architect` agent for placement, classification, integration after a
  code change. Run that skill when the question is *where does this go?*;
  run *this* skill when the question is *is this file good?*
