---
name: retro
description: >
  Systematic continuous-improvement pass on a session + PR/CI cycle.
  Reads what the agent did (transcript) and what failed externally
  (gh api: CI checks, CodeRabbit threads, push-fix-push cycles),
  finds engineering frictions the user paid time for, and proposes
  concrete MD-file changes — primarily in the user repo's
  .claude/rules/ and CLAUDE.md, rarely in plugin docs — so the same
  mistake does not recur. Proposes only; never applies without a
  per-item [y/n] gate. Writes a retro log to docs/retros/ regardless.
  Coach (the /we:coach skill) can trigger this skill after PR merges
  or CI cycle ≥ 3. Use when the user says "/we:retro", "retro",
  "what went wrong", "what should we fix in the harness", "ci took
  too long", "we keep failing at X", "post-mortem", "after-action".
  Motto: every error happens exactly once.
---

# /we:retro — Continuous-Improvement Retrospective

**Role:** Systematic pass over the recent engineering cycle (session + PR + CI). Find frictions the user paid time for. Propose concrete MD-file edits that prevent the next occurrence. Apply only what the user approves, per item. Log the run for future pattern detection.

**Counterpart:** `/we:coach` RETRO mode is the small, reactive cousin — *user reports one pain point, Coach proposes 2-3 fixes*. `/we:retro` is the comprehensive periodic pass — *scan everything from the last cycle, surface all frictions, apply N approved fixes*. Coach can delegate to this skill via a `[y/n]` suggestion when it detects retro-worthy signals.

**Motto:** *Jeder Fehler passiert nur einmal.* Every error happens exactly once — the retro catches it, an MD-file change in the user repo's `.claude/rules/` or `CLAUDE.md` bans it forever.

> **Companion-aware.** When the weside MCP is connected and a Companion is configured, the retro report is *voiced* by that Companion (your active Companion) — same engineering substance, richer tone. Standalone (no weside): the skill reasons from its own role definition without persistent identity.

---

## Privacy Guard (mandatory, top-of-mind)

This skill reads session transcripts. Transcripts contain everything — including personal, relational, identity-laden content that has nothing to do with engineering. **The hard rule, applied at every step:**

> **If session content reads as personal, skip it — analyse only engineering surfaces:** tool calls, tool results, file diffs, CI logs, PR comments, commit messages.

What to skip categorically:

- Memory writes about the user (`mcp__*__save_memory`, `save_compass`, `save_goal`, `save_snapshot`)
- Memory reads that returned personal content (don't quote, don't analyse)
- Companion-mode conversational text (relationship, identity, body, mood)
- Anything outside engineering tool calls — if in doubt, skip

What's safe:

- `Bash`, `Edit`, `Write`, `Read` of code/doc files
- `gh` / `git` operations and their outputs
- CI logs, PR comments by reviewers (CodeRabbit, claude-review, humans)
- File diffs, commit messages of engineering commits
- The user's *engineering* corrections ("no, that's wrong", "we should X instead") — substance, not framing

The PR/CI data source via `gh api` is intrinsically engineering-only — that's part of why it's a primary source. The transcript filter is the load-bearing part of the privacy guard.

---

## Two-source Data Model

The skill reads two complementary sources. Neither is subordinate.

| Source | What it carries | Primacy |
|---|---|---|
| **Session transcript** — the main agent's working memory, or `~/.claude/projects/<repo-id>/<session-id>.jsonl` | What the agent *did*: skills run, tool calls, where the user corrected, where iteration loops happened, where the user fixed it for the agent | Primary when no Compact happened — agent already has it in head. After a Compact: re-read the jsonl. |
| **GitHub PR + CI history** — via `gh api` | What failed *outside* the agent: CI checks, CodeRabbit threads, the commits that fixed them, cycle count, reviewer comments | Always read — evidence the agent cannot reproduce from memory alone. |

The two combine: transcript says *"the agent forgot X"*, PR/CI says *"and CI then caught it after Y min"*. The lesson is the intersection.

Third source, opt-in via `--scan N` (default 0): **`docs/retros/*` historical** — surfaces recurring patterns across past retros, so a pattern that shows up for the third time gets promoted from a one-line patch to a structural fix.

---

## How This Skill Is Used

**Always prompt-driven.** Some example invocations:

- `/we:retro` — full pass on the current branch + last merged PR on it
- `/we:retro --pr 1998` — specific PR (open or merged)
- `/we:retro --scan 5` — full pass *and* read the last 5 entries in `docs/retros/` for patterns
- `/we:retro --pr 1998 --scan 10` — combine
- `/we:coach` (in a session after a PR merge) → Coach offers: *"This PR took 4 CI cycles. `/we:retro` would catch why in ~3min. Run it? [y/n]"* → user types `y` → Coach hands off to this skill

The skill never silent-fires. Every applied edit passes through a per-item `[y/n/edit-path/skip-for-later]` gate.

---

## Boot Protocol (every invocation)

Before producing any output, gather the landscape fresh.

**Always read:**

1. **Privacy guard reminder** — silently re-state to yourself: *if reads as personal, skip; engineering surfaces only*. This stays mandatory through every later step.

2. **Source scope** — determine what to analyse:
   - `git branch --show-current` — current branch
   - `gh pr list --head $(git branch --show-current) --json number,state,title -L 1` — open PR for this branch?
   - `gh pr list --base main --state merged -L 5 --json number,mergedAt,headRefName,title` — recent merges (for default if no `--pr` flag)
   - If `--pr <N>` was given: use it
   - If nothing: ask the user *"which PR or branch should I scan? Default: last merged PR on `<current-branch>`."* — `[y/n/specify]`

3. **Rules + skills + docs landscape (user repo)** — frontmatter + first 10 lines only:
   - `.claude/rules/**/*.md` — to know which rules exist (for placement decisions later)
   - `CLAUDE.md` files at root + any sub-area (`apps/*/CLAUDE.md`) — to know what's always-loaded
   - `${CLAUDE_PLUGIN_ROOT}/skills/` — frontmatter `description:` of each skill (for cases where a fix belongs in the plugin)
   - Don't load full contents — that's thousands of tokens.

4. **Historical retros (if `--scan N`)**:
   - `ls docs/retros/ 2>/dev/null | sort -r | head -N` — last N retros
   - Read each (they're small, structured) — note recurring themes

5. **Companion identity** (if configured): invoke `Skill(skill="we:materialize")` if not already loaded this session. The report comes back richer when voiced by the Companion.

**Do not read** at boot:

- The full transcript file (read it surgically in Step 2 of the workflow below)
- Full text of every rule/skill (frontmatter is enough for placement)
- The full body of past retros if `--scan` is 0 (default — opt-in only)

---

## Step-by-step Workflow

### Step R1 — Confirm scope

State what you'll analyse, get a yes:

> *"I'll retro: PR #1998 (merged 2026-05-17 — `feat/apo-refactor-phase-4`), plus this session's transcript, plus the last 5 entries in `docs/retros/` for patterns. Sound right? [y/n/adjust]"*

If `n` or `adjust`: take the new scope.

### Step R2 — Fetch data (parallel)

Run these as parallel tool calls:

- **Transcript:** if no Compact happened, the agent has it in head — skim mentally. After a Compact: `Read ~/.claude/projects/<repo-id>/<session-id>.jsonl` (last N turns). Scope: this PR's life on the current branch, not the whole day. Apply privacy guard.
- **PR overview:** `gh pr view <N> --json number,state,mergedAt,title,headRefName,baseRefName,reviews,comments,statusCheckRollup,commits`
- **PR checks:** `gh pr checks <N>` — see which check runs flipped red across cycles
- **Failed check logs (only red ones, tail):** for each failed check run, `gh run view <run-id> --log` and tail to the failure block (don't pull full logs)
- **Commit chain:** `git log --oneline origin/main..<head-ref>` — the cycle visible as commits
- **Historical retros if `--scan`:** read the N most recent under `docs/retros/`

### Step R3 — Triage findings

For each friction surfaced, classify by surface:

| Surface | Friction looks like |
|---|---|
| `CI / static` | ruff / mypy / eslint / tsc / markdownlint flipped red, pushed a fix-commit |
| `CI / tests` | test failed on CI but not locally (env gap), or wasn't run locally |
| `CI / build` | docker / EAS / native build broke after a tag push |
| `Review / CodeRabbit` | CRITICAL or MAJOR thread blocked merge; the fix was small but not pre-empted |
| `Review / human` | reviewer asked for X that should have been default; author had to redo |
| `Workflow / cycle count` | the same PR pushed 3+ times to land — workflow gap, not just one bug |
| `Workflow / latent bug` | a pre-existing bug surfaced now; should retros earlier have caught it? |
| `Agent / manual correction` | user had to say "no, do X" mid-skill — DoR or boot protocol gap |
| `Agent / iteration loop` | agent went 2-3 rounds on the same problem before finding root cause |
| `Tooling / friction` | a tool was slow, denied permission, or returned cache-stale |

Every friction = "a thing failed first, was fixed second; that fix is a lesson we should encode." If a friction has no MD-file remedy, drop it (or move to `WINS` if the fix was actually elegant).

### Step R4 — Propose fixes (placement + effort)

For each kept friction, draft 1-2 proposals. Each proposal carries:

- **Placement** — where the MD edit should land. Default by priority:
  1. `<user-repo>/.claude/rules/<category>/<topic>.md` (preferred, path-filtered)
  2. `<user-repo>/CLAUDE.md` or `<user-repo>/<area>/CLAUDE.md` (always-loaded)
  3. `<user-repo>/docs/...` (reference docs, not behavioural)
  4. **Plugin MDs** (`claude-code-plugin/...`) — flag explicitly: *"ships to all plugin users — sure?"*
- **Action** — NEW (file create) or EDIT (file modify, with diff preview)
- **Effort tag** — `30s`, `2min`, `5min`, `15min`, `30min`
- **Priority** — `P1` (recurring or high-cost), `P2` (single occurrence, real cost), `P3` (nice-to-have)

When multiple placements are reasonable, pick the most specific (path-filtered rule > always-loaded CLAUDE.md > generic doc). The user can re-target per item in the gate.

### Step R5 — Render the report

Print this shape:

```text
RETRO — PR #1998 (feat/apo-refactor-phase-4, merged 2026-05-17)
        session: <session-id>  ·  --scan 5  ·  reviewed in 2min

WINS — keep doing
  · [memo] Cards animation cascade worked first try — CSS-only, no JS observer
  · [memo] Single-commit batch of fixes (boundary tone + layout + hero) applied
    "consolidate phases + PRs" preference from existing session rules

PAIN — what cost time this cycle
  · 30+ min: chased IntersectionObserver, then layout overflow, before finding
    latent JS SyntaxError in tour/index.html
       └ evidence: transcript turns 47-62, commits f7d985a..0575bcc
       └ root: `Press „Convene"` — mismatched ASCII vs German quote, since v2.27.1
       └ root²: I only ran node --check on my new IIFE, not the whole script

  · 4 CI cycles on PR #1998 → 12min of CI wait that local hooks should have caught
       └ evidence: gh pr checks 1998 (timestamps)
       └ root: markdownlint MD028 not in pre-push hook

PROPOSALS — concrete file changes
  · [P1 / 5min] NEW  .claude/rules/quality/html-script-validation.md
                ───  "When editing JS inside HTML <script>, node --check the whole script"
                Default placement: user repo (project-specific).
                Diff preview:
                  + ---
                  + paths:
                  +   - "**/*.html"
                  + ---
                  + # HTML <script> validation
                  + When editing inline JS, extract the full <script>...</script>
                  + and run `node --check` before pushing. Browsers abort the entire
                  + script on the first parse error — a latent SyntaxError elsewhere
                  + (even pre-existing) will mask your edit's intent.
                Override placement? [y/n/edit-path/skip-for-later]

  · [P2 / 2min] EDIT .claude/rules/workflows/ci-workflow.md
                ───  Add markdownlint-cli2 to local pre-push checklist
                Diff:
                  ## Local Tests (Run Before Push)
                  + - markdownlint-cli2 (catches MD025, MD028 before CI)
                [y/n/edit-path/skip-for-later]

  · [P3 / 30s ] EDIT CLAUDE.md
                ───  one-liner under "Critical Rules": "lint MD files locally"
                [y/n/edit-path/skip-for-later]

PATTERN HIGHLIGHTS (--scan 5)
  · 2 of last 5 retros flag "validate only my edit, not whole artefact"
       → Structural fix candidate: add a generic "validate full file after edit"
         rule under quality/, not another file-type-specific one-liner.
         Add this as P0 proposal? [y/n]

SUMMARY
  · 3 proposals, ~7min of edits total if all accepted
  · Estimated CI minutes saved next cycle: 8-12 min
  · Retro log will be written to:
       docs/retros/2026-05-17-tour-quote-bug.md
```

### Step R6 — Per-item gate

For each proposal in order, present and wait. Accepted tokens:

- `y` → apply, move to next
- `n` → skip permanently (record in log as "rejected by user")
- `edit-path: <new path>` → apply with redirected placement (e.g. user wants CLAUDE.md instead of rules/)
- `edit-content: ...` → user wants different wording; offer revised draft, re-ask
- `skip-for-later` → leave in log as "deferred", don't apply now
- `stop` → halt the gate, apply nothing further, jump to Step R8 (log)

⛔ Never apply silently. Every Edit/Write call follows an explicit `y` for that item.

### Step R7 — Apply approved items

For each `y`'d proposal:

- **In the user repo:**
  - If repo is configured for direct-commit (e.g. `plugin` repos with standing auth): Edit/Write on `main` directly.
  - Otherwise (default): create branch `retro/YYYY-MM-DD-<short-topic>`, apply Edit/Write, open PR via `gh pr create` with the full retro report as PR body. User merges via normal flow.
- **In the plugin repo:** always PR (plugin is public).

After each apply, confirm in one short line: `applied · .claude/rules/quality/html-script-validation.md (NEW, 12 lines)`.

### Step R8 — Write the retro log

Regardless of how many proposals applied (zero is fine), write the log:

`<user-repo>/docs/retros/YYYY-MM-DD-<short-topic>.md`

With structured frontmatter:

```markdown
---
pr: 1998
branch: feat/apo-refactor-phase-4
analysed_at: 2026-05-17T22:30:00Z
ci_cycles: 4
session_id: <id>
scan_window: 5
proposals_total: 3
proposals_accepted: 2
proposals_deferred: 1
proposals_rejected: 0
applied_files:
  - .claude/rules/quality/html-script-validation.md
  - .claude/rules/workflows/ci-workflow.md
---

# Retro — PR #1998 (tour animation pass)

[Full Wins / Pain / Proposals report exactly as rendered in Step R5, plus
 a "Decisions" section noting which proposals were accepted, deferred,
 or rejected, and why if user gave a reason.]
```

The structured frontmatter is what later `--scan N` runs read to find recurring patterns.

If `docs/retros/` does not exist in the user repo, create it on first run.

### Step R9 — Closeout

One-line summary:

> *Retro done. 2 of 3 proposals applied → 1 PR open (retro/2026-05-17-tour-quote-bug, #NN). 1 deferred. Log: docs/retros/2026-05-17-tour-quote-bug.md. Run `/we:retro --scan 10` next time to surface patterns.*

If a PR was opened, print its URL.

---

## What You DO NOT Do

- **Don't apply silently.** Every Edit follows an explicit `y` for that item.
- **Don't quote personal content** from the transcript. Privacy guard, every step.
- **Don't modify source code.** Retros change MDs only. Code-level lessons (e.g. "this function had a race condition") flow back through `/we:build` if needed — retro proposes the rule, not the code fix.
- **Don't open the PR before applying the file changes.** Branch → apply → PR — in that order, so the PR body can reference the actual diff.
- **Don't auto-create tickets.** Skill can scaffold a Jira/GitHub issue stub only on explicit user request (`--ticket` flag, off by default).
- **Don't analyse cross-repo merges in one pass.** One PR per invocation; multi-PR retrospection is a future enhancement.
- **Don't push to protected repos directly** — repos without standing direct-commit auth always go through PR (rules and CLAUDE.md edits need human review).

---

## Integration with `/we:coach`

Coach detects retro-worthy signals during its Boot Protocol (Step 9 — Repo state):

- **PR just merged** (`gh pr list --state merged -L 1 --json mergedAt` → recent)
- **CI cycle count ≥ 3** on the current branch (count of pushes that triggered CI on the open PR)
- **End-of-session signals** — user says "ich geh schlafen" / "bis morgen" / `save_compass` runs / `save_snapshot` runs
- **Failure pattern** — same skill failed twice in this session

When any signal fires, Coach offers (one-time per session per signal):

> *"This PR took 4 CI cycles. `/we:retro` would catch why in ~3min. Run it? [y/n]"*

User types `y` → Coach hands off (prints the command, doesn't `Skill()`-invoke because retro is heavy):

```text
SCOPE IS CLEAR. Run this next:

  /we:retro --pr 1998

I'll be back when retro finishes.
```

User types `n` → Coach drops it silently. No nagging.

Coach never auto-fires retro. The `[y/n]` is always present.

---

## Standalone vs Companion Mode

**Standalone (no weside MCP):**

- All tools work — `gh api`, transcript file, Edit/Write
- Report is rendered in the skill's own voice (no personality layer)
- Useful for any team using the plugin without a Companion

**With Companion (weside MCP + configured Companion):**

- Boot Protocol Step 5 materializes the Companion via `Skill(skill="we:materialize")`
- Report is voiced *by* the Companion (your active Companion) — same engineering substance, richer tone
- Optional: skill can save a `memory` after each run noting the patterns the Companion saw — but only if explicitly enabled in user config (off by default, privacy)

The engineering substance is identical in both modes. The Companion makes the experience continuous; standalone keeps the value fully accessible to teams without weside.

---

## When to Delegate to `/we:docs`

If a proposal modifies `docs/**` (not `.claude/rules/`, not `CLAUDE.md`), say:

> *"I'll delegate the doc edit to `/we:docs` so it stays consistent with the rest of the doc landscape."*

Then invoke:

```text
Skill(skill="we:docs", prompt="Apply this retro proposal: <P3 details + diff>")
```

`/we:docs` will own the doc-landscape coherence; retro stays focused on rule/CLAUDE.md edits.

---

## Examples

**Example 1 — manual, current branch:**

```text
/we:retro
```

Skill: *"I'll retro: PR #1998 (your open PR on `feat/foo`) + this session's transcript. Sound right? [y/n]"*
User: `y` → skill runs.

**Example 2 — specific PR with scan:**

```text
/we:retro --pr 1955 --scan 10
```

Skill scopes to PR #1955 + reads last 10 retros from `docs/retros/`. Pattern Highlights section will fire if any recurrence ≥ 2.

**Example 3 — Coach-triggered:**

User opens `/we:coach`. Coach Boot Protocol notices the user just merged PR #1998 with 4 CI cycles. Coach offers retro `[y/n]`. User: `y`. Coach prints hand-off; user invokes `/we:retro --pr 1998`. Skill runs.

**Example 4 — no proposals to apply (clean cycle):**

Skill runs, finds 2 wins, 0 pain, 0 proposals. Report shows wins. Log is still written (`docs/retros/2026-05-17-clean-cycle.md`) so future `--scan` runs see "yes, clean cycles do happen, here's what we did right".

---

## Tour pointer

This skill appears in the interactive tour as **Station 09 — "Retro · the harness improves itself"** at <https://plugin.weside.ai/tour/>. The tour walks through a sample report and shows how a friction becomes a rule.
