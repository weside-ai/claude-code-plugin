---
name: doc-improve
description: Use when reviewing one or more existing documentation files for substantive content improvement — claims drifted from implementation, redundancy with sibling docs, stale plans, content that can be deleted, missing reader context. Operates on a single file, multiple files, or a glob. For Claude Code rules in `.claude/rules/`, additionally enforces token-efficiency and path-pattern correctness.
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

1. `.claude/rules/quality/doc-standards.md` — full body. This rule defines:
   the 4-layer knowledge system, `docs/` tree structure, doc-format templates
   (architecture, journey, primitive-detail), TurboVault frontmatter standard,
   placement decision tree, promotion criteria, rules structure, size
   guidelines. **Reference it; do not duplicate it.** When you propose a
   change, cite the rule by section.
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
| `**/we/skills/*/SKILL.md`, `**/agents/*.md` | Skill / Agent | (no reference — apply universal pillars only) |

If a file falls outside all of these (e.g. a `README.md` at repo root that
isn't `CLAUDE.md`): apply the universal pillars only, note in the verdict
that this file has no documented home in the conventions.

---

## The Four Universal Pillars

Apply these to **every** file. They are the substance. Type-specific reference
docs add a fifth pillar layer on top, they don't replace these.

### Pillar 1 — Architectural Correctness

**Question:** Is what this doc claims still true in the code?

**Method:** Extract every factual claim that names a path, function, class,
field, command, or behaviour. For each, verify against the source:

- `ls <path>` — does the directory exist with the named contents?
- `grep -n "def <name>\|class <name>" <path>` — does the symbol exist?
- `grep -rn "<imported_name>" <searchroot>` — is the import live?
- `git log -1 --format="%ai %s" <path>` — when did this last change?

Catch what humans miss: a directory rename (`adapters/` → `channels/`), a
field deleted from a dataclass, a middleware count drift, an API method that
got added but isn't documented, a "Phase 2" plan section describing work
that was abandoned or already shipped.

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

**Method:**

```bash
git log -1 --format="%ai" <doc>             # When was the doc last edited?
git log --oneline --since=<doc-edit-date> -- <code-path-it-describes>
```

If the code path has moved a lot since the doc edit, the doc is at risk —
look harder at the affected sections. Don't fail a doc just for being older
than the code, but use this as a search beam for Pillar 1 verification.

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

(Repeat for each finding. Severity tiers: **BLOCKER** · **MAJOR** · **MINOR** · **NIT**.)

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

---

## Anti-Patterns and Rationalisations

Do not do any of these. These are the failure modes that make a doc review
feel productive but deliver nothing.

| Rationalisation | Reality |
|---|---|
| "The doc looks fine, the structure is good" | Structure ≠ content. Run Pillar 1 anyway. Drift is invisible from the surface. |
| "I'll suggest frontmatter improvements" | Out of scope unless the missing frontmatter blocks TurboVault indexing. Frontmatter is `doc-architect`'s job. |
| "I'll fix all the broken links" | Out of scope. Links are mechanical; the user said *content* matters more. |
| "I'll add a TODO for the team" | No. The skill writes findings, not TODOs. If something is missing, propose its addition or its deletion. |
| "I'll cite the doc, not the code" | Code is truth, doc is description. Cite the code. |
| "I'll rewrite from scratch" | Almost always wrong. Most reviews are TIGHTEN / surgical-fix; full rewrites are rare. Default to surgical. |
| "I won't run grep, I remember this codebase" | Memory is not evidence. Run grep. Hallucinated findings destroy trust faster than missed findings. |
| "Three findings is too few — let me add some MINOR ones" | Padding hurts. If a doc has three real findings, report three. |
| "I'll write a finding for the future plan section" | Only if the plan items are silently shipped / abandoned (currency check). "Plan section exists" is not a finding. |
| "I'll skip Pillar 3 if the file looks self-contained" | Don't. The redundancy check is one of the highest-value pillars. Sibling-doc duplication is the most common drift cause. |

---

## Apply Loop (after approval)

For each approved finding, in order:

1. Edit the file.
2. If the finding lists downstream impact (same drift in another file), ask
   the user "fix downstream too?". If yes — extend the loop to cover the
   downstream file using the same diff.
3. If a primitive bypass annotation was added or removed: regenerate
   `docs/architecture/BYPASS-REGISTER.md` via
   `bash scripts/generate-bypass-register.sh --write` (this is `doc-architect`
   territory but the skill knows when to flag it).
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
