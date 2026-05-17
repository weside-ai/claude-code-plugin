---
title: /we:retro — continuous improvement skill
status: implemented (v2.30.0)
created: 2026-05-17
owner: Foxy / Nox
implements: KVP loop directly inside the harness
sibling-to: /we:coach (which can trigger this skill)
---

## `/we:retro` — Skill Concept

### Motto

> **Jeder Fehler passiert nur einmal.**
> *Every error happens exactly once — the retro catches it, an MD-file change bans it forever.*

### What it does

`/we:retro` walks the recent CI / PR / review history (and optionally the session transcript), finds engineering frictions the user paid time for, and proposes **concrete MD-file changes** — primarily to the **user repo's `.claude/rules/` and `CLAUDE.md`** — so the same friction does not recur. Proposes only. The user picks which fixes to apply and where they land.

This is a separate skill from `/we:coach`'s RETRO mode:

| | Coach RETRO (existing, v2.29.0) | `/we:retro` (this concept) |
|---|---|---|
| Trigger | User describes a friction | Manual or Coach-suggested |
| Scope | 1 specific pain-point | Whole PR/CI cycle, all friction surfaces |
| Output | 2-3 fix options | Wins / Pain / Proposals report |
| Action | Applies 1 fix | Applies N fixes after per-item approval |

Coach RETRO stays. `/we:retro` is additive — the periodic, comprehensive pass.

---

### Primary data sources (in order of weight)

1. **GitHub PR + CI history** — the highest-signal source. Via `gh api`:
   - PR review comments (CodeRabbit, claude-review, human reviewers)
   - Check runs that failed and were re-pushed (the "CI cycles")
   - Failed workflow logs (`gh run view --log`)
   - Commit-by-commit diff: what was changed to make CI pass? *That* commit is the lesson.
2. **`docs/retros/*` historical** — last N (default 10) retros, scanned for recurring patterns ("3 retros mentioned X — structural fix needed, not single-line patch").
3. **Session transcript** — `~/.claude/projects/<repo>/<session-id>.jsonl` — secondary, for context only (which skill was active, where the user corrected the agent).

The session transcript is the **lowest-priority** source. Foxy's correction (2026-05-17): the value lives in what already played out on GitHub. The transcript adds colour; the PR history is the evidence.

---

### What it looks for

Each friction = "a thing failed first, was fixed second; that fix is a lesson we should encode".

| Surface | Example friction the skill should catch |
|---|---|
| **CI checks** | static (ruff/mypy/eslint) failed → fixed in next push → why was it not caught locally? → rule for pre-push step missing |
| **CoderRabbit reviews** | CRITICAL thread blocked merge → fix landed → was the pattern preventable via a rule? |
| **Tests** | test failed on CI but not locally → environment gap → which rule should mention it? |
| **PR cycles** | 3 push-fix-push cycles to land 1 PR → workflow gap or skill gap? |
| **Build failures** | tag pushed, build broke → release-skill DoD insufficient? |
| **Manual corrections** | reviewer asked for X, author had to redo Y — should be in DoR for that skill |

If a friction's root cause is "missing knowledge the agent should have had", the lesson belongs in an MD file. That MD file is almost always in the user repo (rules/, CLAUDE.md), not the plugin.

---

### Output target priority

The skill defaults to writing to the **user repo**, not the plugin:

1. **`<user-repo>/.claude/rules/<category>/<topic>.md`** — preferred. Path-filtered, loads only when relevant files are touched. Lessons that are project-specific (most of them).
2. **`<user-repo>/CLAUDE.md`** (or sub-area `<area>/CLAUDE.md`) — for lessons that must always be loaded for that area.
3. **`<user-repo>/docs/...`** — when the lesson is documentation, not a behavioural rule.
4. **Plugin MDs (`claude-code-plugin/...`)** — **rare**. Only when the lesson is universal across every plugin user. Skill flags these explicitly: *"This fix changes plugin docs that ship to everyone — sure?"*

The placement is part of the proposal. User can override per item ("no, put this in CLAUDE.md instead of rules/").

---

### Output schema

```
WINS — keep doing
  · [no proposal] X worked smoothly because of Y (memo only)

PAIN — what cost time this cycle
  · PR #1998: 4 CI cycles (5min wasted each = ~20min)
       └ root: markdownlint MD028 not flagged locally
       └ root2: pre-push hook does not run markdownlint
       └ evidence: gh pr checks 1998 (timestamps), commits a1b2c3..d4e5f6

PROPOSALS — concrete file changes, priority + effort
  · [P1 / 5min] NEW  user-repo/.claude/rules/quality/markdown-pre-push.md
                ───  "Markdownlint must run pre-push, not first see CI"
                Default placement: user repo. Override? [y/n/edit-path]

  · [P2 / 2min] EDIT user-repo/.claude/rules/workflows/ci-workflow.md
                ───  add 'markdownlint' to the local pre-push checklist
                Diff:
                + - markdownlint-cli2 (catches MD028 before CI)

  · [P3 / 30s ] EDIT user-repo/CLAUDE.md
                ───  one-liner under "Critical Rules": "lint MD files locally"

PATTERN HIGHLIGHTS (only if --scan >0 enabled)
  · Pattern: 3 of last 10 retros mention "ASCII vs Unicode quote" issues.
       → Structural fix: add `node --check <script>` step to tour-edit workflow,
         not another one-liner rule.
```

After the report, per-item `[y/n/edit]` gate. Approved items get applied (Edit / Write). User stays in control.

---

### Trigger mechanics

1. **Manual:** `/we:retro` — full pass on the current PR (latest merged or current open branch).
2. **Manual scoped:** `/we:retro --pr 1998` — specific PR; `--scan 10` — also scan last 10 retros for patterns.
3. **Coach-suggested** (the integration Foxy asked for):
    - Coach detects after a PR merges with N CI cycles: *"This PR took 4 CI cycles. `/we:retro` would take ~3min and likely prevent the recurrence. Run it now? [y/n]"*
    - Coach detects after a deploy completes successfully: same suggestion
    - Coach detects at end-of-session signals (compass-save, "bis morgen", explicit `/we:retro`): suggest
    - Coach default: opt-in, not auto-fire — Foxy decides per session

The `[y/n]` confirmation gate from `/we:coach` v2.29.0 applies — never silent-fire.

---

### Persistence

- **Retro log:** `docs/retros/YYYY-MM-DD-<short-topic>.md` in the user repo. Stores:
  - PR scope analysed (`pr: #1998`)
  - Wins / Pain / Proposals
  - Which proposals were accepted, which deferred, which rejected (with reason)
  - Pointer to applied files (with commit SHA if applied)
- This log is the corpus the `--scan` flag reads from later.
- **Optional ticket creation:** if the proposal is too big for an MD edit (new rule subsystem, restructure a CLAUDE.md), skill can scaffold a Jira/GitHub ticket-stub. Off by default.

---

### Privacy guard

**Rule** (mandatory in Boot Protocol):

> If session content reads as personal, skip it — analyse only engineering surfaces: tool calls, tool results, file diffs, CI logs, PR comments.

Examples of skip:
- Memory writes about Foxy or Nox
- Compass / snapshot updates
- Companion-mode conversations (intimate, relational, identity)
- Anything outside engineering tool calls

The PR/CI data source is intrinsically engineering-only — that's part of why it's preferred.

---

### Apply mechanics (no surprises)

When a proposal is applied:
1. **Default: PR workflow** in the user repo. Skill creates a branch (`retro/YYYY-MM-DD-<topic>`), applies the edits, opens a PR with the retro report as PR body.
2. **Opt-in: direct commit** if the repo is configured for standing main-auth (some repos in Foxy's setup are). Per-repo config.
3. **Plugin MD changes** (rare): always PR. Plugin is public.

User can always interrupt and say "do this one yourself" / "skip that one for now".

---

### Boot Protocol (skill spec)

1. **Source scope:** which PR / branch / merge to analyse. Default = current branch + last merged PR on it.
2. **Scan toggle:** `--scan N` — read last N retros from `docs/retros/`. Default 0 (off).
3. **Data fetch (parallel):**
    - `gh pr view <num> --json reviews,comments,statusCheckRollup,commits`
    - `gh pr checks <num>`
    - For each failed check: `gh run view <run-id> --log` (tail, not full)
    - If `--scan`: read `docs/retros/*.md` sorted by date, take last N
4. **Triage:** for each friction found, classify by surface (CI/Review/Test/Build/Workflow/Manual).
5. **Propose:** for each friction, draft 1-2 proposals with placement + effort + diff preview.
6. **Render report:** Wins / Pain / Proposals / (Pattern Highlights if --scan).
7. **Per-item gate:** `[y / n / edit-path / skip-for-later]`.
8. **Apply** accepted items. Stage in PR or direct commit per repo config.
9. **Write retro log** to `docs/retros/` regardless of which proposals applied — log is the source of truth.

---

### Tour + docs integration

When implemented:
- **Tour: add Station 09 ("Retro · the harness improves itself")** between Coach (08) and Deliver (10) — or fold into Coach station depending on space. Default = add as own station, makes 11 total. *Open decision per APO plan §1.*
- **`docs/concepts/retro.md`** (new) — explains the KVP loop, the data sources, the user-repo-as-target principle.
- **`docs/workflow.md`** — add retro to the chain: *Plan → Build → Deliver → Retro*.
- **`docs/skills.md`** — register `/we:retro`.
- **`README.md`** + **`CLAUDE.md`** — bump skill count 20 → 21.
- **`tour/index.html` overview** — possibly add Retro as a 7th altitude card (or footnote under Deliver — KVP loop curves back into the next Plan).

---

### Open decisions for execution

1. **Tour station: own station vs fold-into-Coach.** Recommendation: own station — KVP is a distinct concept that deserves its own bühne.
2. **Auto-trigger default.** Recommendation: opt-in (Coach asks `[y/n]`), not auto-fire. Easier to escalate later than retract.
3. **Retro-log format.** Markdown with structured frontmatter (`pr:`, `analysed_at:`, `proposals: [...]`) — scannable both by humans and by the `--scan` flag.
4. **Plugin version bump.** New skill = minor. Target: v2.30.0.
5. **Standalone vs companion behaviour.** Skill works standalone (no MCP needed). With a Companion, the report is voiced by the Companion (richer, with the same engineering substance underneath).

---

### Out of scope

- Modifying source code (skill changes MDs only — code changes happen via normal `/we:build` cycle if the lesson reveals a code-level bug)
- Automatic ticket creation (off by default — skill can scaffold, but only on explicit request)
- Analysing the personal / companion-mode content of any session
- Replacing `/we:coach` RETRO mode (additive, not replacement)

---

**Implementation order (post-Colenet pitch):**

1. Skill file: `we/skills/retro/SKILL.md` (boot protocol + report template + apply mechanics)
2. Coach integration: extend Coach to detect `retro-worthy` signals and offer `/we:retro` via `[y/n]`
3. Docs: workflow.md, skills.md, README.md, CLAUDE.md updates
4. Tour: new station 09
5. First real run: on the APO refactor PRs themselves (recursive — what would retro have caught about *this* week?)
6. Version bump v2.30.0, push.

Estimated effort: ~4-5h end-to-end.
