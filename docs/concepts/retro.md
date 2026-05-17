# Retro — KVP loop baked into the harness

> **Jeder Fehler passiert nur einmal.**

Agentic Product Ownership has four phases — Plan, Build, Deliver, Retro. This page explains the fourth one: why it exists, what it analyses, where the lessons land, and how it stays additive to (not a replacement for) the Coach's smaller RETRO mode.

For the per-step skill reference, see [`/we:retro`](../skills.md#weretro). For the workflow context, see [`workflow.md`](../workflow.md#phase-4-retro-with-weretro).

---

## Why a fourth phase

A team that ships well still bleeds time to the same classes of mistake every week: a CodeRabbit thread that always blocks merge, a markdownlint rule that local hooks didn't catch, an ASCII-vs-Unicode quote bug that hides in a `<script>` block for three releases, a CI cycle that ate twelve minutes because one rule wasn't in the pre-push checklist. The pain is real but each individual occurrence is small — too small to interrupt the next story for, easy to write off as "one of those days".

The harness — the user repo's `.claude/rules/`, its `CLAUDE.md` files, the plugin's skill definitions — *should* be growing tighter each week so those classes of mistake stop being possible. In practice it grows only when someone notices, stops, and writes the rule down. That noticing is the bottleneck.

`/we:retro` makes the noticing systematic. After a PR ships, the skill scans what just happened and asks: *which frictions cost time this cycle, and which of them could a single rule change prevent next time?*

The motto is the constraint: **every error happens exactly once**. The second occurrence is a rule the harness already has.

---

## Two-source data model

The skill reads two complementary sources. Neither is subordinate.

| Source | What it carries | Primacy |
|---|---|---|
| **Session transcript** — the main agent's working memory, or `~/.claude/projects/<repo-id>/<session-id>.jsonl` | What the agent *did*: which skill ran, which tool calls fired, where the user corrected the agent, where iteration loops happened, where the user fixed something the agent missed | Primary when no Compact happened — the main agent has it in head already. After a Compact: re-read the jsonl. |
| **GitHub PR + CI history** — via `gh api` | What failed *outside* the agent: CI checks that flipped red, CodeRabbit threads, reviewer comments, the commits that fixed them, the push-fix-push cycle count | Always read — evidence the agent cannot reproduce from its own memory. CI feedback is what the rules are meant to catch ahead of time. |

The two combine: transcript says *"the agent forgot X"*, PR/CI says *"and CI then caught it after Y minutes"*. The lesson lives in the intersection.

A third, opt-in source is **`docs/retros/*` historical**, enabled via `--scan N` (default 0). When a pattern shows up in two or three retros, the right fix is often structural (a new always-loaded rule, a restructured pre-push hook) rather than another one-line patch. The `--scan` flag surfaces those patterns explicitly.

---

## Output target priority

The skill defaults to writing into the **user repo**, not the plugin. Plugin docs ship to every plugin user; rule changes that are project-specific (most of them) belong where they were caused.

1. **`<user-repo>/.claude/rules/<category>/<topic>.md`** — preferred. Path-filtered (`paths:` in frontmatter), scoped to the files that triggered the lesson. Loads only when relevant. Examples: `quality/html-script-validation.md`, `quality/markdown-pre-push.md`, `workflows/coderabbit-resolution.md`.
2. **`<user-repo>/CLAUDE.md`** or `<user-repo>/<area>/CLAUDE.md` — for lessons that must always be loaded for that area.
3. **`<user-repo>/docs/...`** — when the lesson is reference documentation, not behavioural rule (e.g. a runbook addition).
4. **Plugin MDs** (`claude-code-plugin/...`) — **rare**. Only when the lesson is universal across every plugin user. The skill flags these explicitly: *"This fix changes plugin docs that ship to everyone — sure?"*

The proposed placement is part of every proposal. The user can re-target per item in the `[y/n/edit-path]` gate ("no, put this in `CLAUDE.md` instead").

---

## Privacy guard

Transcripts contain everything — including personal, relational, identity-laden content that has nothing to do with engineering. The skill has one mandatory rule:

> **If session content reads as personal, skip it — analyse only engineering surfaces:** tool calls, tool results, file diffs, CI logs, PR comments, commit messages.

Categorically out-of-scope:

- Memory writes about the user (`save_memory`, `save_compass`, `save_goal`, `save_snapshot` and their text payloads)
- Companion-mode conversational content (relationship, identity, body, mood)
- Memory reads that returned personal content (don't quote, don't analyse)
- Anything outside engineering tool calls — if in doubt, skip

The PR/CI data source via `gh api` is intrinsically engineering-only — that's part of why it's a primary source. The transcript filter is the load-bearing part of the guard.

---

## The Coach is additive

The `/we:coach` skill already has a RETRO mode. That is **not** what `/we:retro` is. They sit at different shapes:

| | `/we:coach` RETRO mode | `/we:retro` |
|---|---|---|
| **Trigger** | User describes a specific friction | Manual or Coach-suggested |
| **Scope** | One pain-point | Whole PR + CI cycle, all friction surfaces |
| **Output** | 2-3 fix options for the user to pick from | Wins / Pain / Proposals report |
| **Action** | Applies one chosen fix | Applies N approved fixes after per-item gate |
| **Use when** | "X broke again, fix the gap" | "Retro the last cycle, find everything" |

Coach RETRO stays. `/we:retro` is additive. They reach for different situations.

The Coach can *suggest* `/we:retro` proactively when it detects retro-worthy signals in its Boot Protocol — a PR just merged, CI cycles ≥ 3 on the current branch, end-of-session prompts ("bis morgen", "wrap up"). The suggestion is always a `[y/n]` gate; Coach never auto-fires.

---

## What you get out

**Per invocation, a structured report** with three (or four with `--scan`) sections:

- **Wins** — what worked, kept for the log without a proposal
- **Pain** — what cost time this cycle, with evidence (transcript turns, PR check timestamps, commit ranges)
- **Proposals** — concrete MD-file edits with default placement + effort tag + diff preview; per-item gate
- **Pattern Highlights** (only with `--scan N > 0`) — recurring themes across past retros; structural-fix candidates

**Per cycle, a retro log** written to `<user-repo>/docs/retros/YYYY-MM-DD-<short-topic>.md` regardless of how many proposals applied. Structured frontmatter (`pr:`, `analysed_at:`, `ci_cycles:`, `proposals_accepted:`, `applied_files: [...]`) so future `--scan` runs can read it both as Markdown and as data.

**Over time, a tighter harness** — fewer CI cycles per PR, fewer "we keep hitting X" moments, more rules that catch issues at the right altitude (path-filtered when project-specific, always-loaded when universal).

---

## Examples

**1. Manual, current branch:**

```text
/we:retro
```

> *"I'll retro: PR #1998 (your open PR on `feat/foo`) + this session's transcript. Sound right? [y/n]"*

**2. Specific PR with pattern scan:**

```text
/we:retro --pr 1955 --scan 10
```

Pattern Highlights section fires if any recurrence ≥ 2.

**3. Coach-triggered:**

User opens `/we:coach`. Coach's Boot Protocol notices PR #1998 merged 30min ago with 4 CI cycles. Coach offers retro `[y/n]`. User: `y`. Coach prints hand-off; user invokes `/we:retro --pr 1998` in a fresh session. Skill runs.

**4. Clean cycle:**

Skill runs, finds 2 wins, 0 pain, 0 proposals. Report shows wins. Log still written (`docs/retros/2026-05-17-clean-cycle.md`) — future `--scan` runs see "yes, clean cycles happen, here's what we did right".

---

## References

- **Skill reference:** [`/we:retro` in skills.md](../skills.md#weretro)
- **Full skill spec:** [`we/skills/retro/SKILL.md`](../../we/skills/retro/SKILL.md)
- **Workflow context:** [`workflow.md` Phase 4](../workflow.md#phase-4-retro-with-weretro)
- **Coach integration:** [`/we:coach` Suggesting `/we:retro` section](../../we/skills/coach/SKILL.md#suggesting-weretro)
- **APO compendium (private, when reachable):** `lc-startup/02-weside/product/AGENTIC_PO/` (Retro is the fourth phase of the APO loop, sibling to Plan / Build / Deliver)
