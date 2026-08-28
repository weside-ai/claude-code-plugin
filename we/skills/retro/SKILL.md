---
name: retro
description: >
  Systematic retrospective on a session + PR/CI cycle — finds frictions
  from transcript + gh api, proposes concrete .claude/rules/ and
  CLAUDE.md edits behind a per-item [y/n] gate, logs to docs/retros/.
  Use when the user says "/we:retro", "retro", "post-mortem",
  "what went wrong", "ci took too long", "we keep failing at X".
---

# /we:retro — Continuous-Improvement Retrospective

**Role:** Systematic pass over the recent engineering cycle (session + PR + CI). Find frictions the user paid time for. Propose concrete MD-file edits that prevent the next occurrence. Apply only what the user approves, per item. Log the run for future pattern detection.

**Motto:** *Jeder Fehler passiert nur einmal.* Every error happens exactly once — the retro catches it, an MD-file change in the user repo's `.claude/rules/` or `CLAUDE.md` bans it forever.

> **Companion-aware:** report voiced by the active Companion when one is materialised — see `${CLAUDE_PLUGIN_ROOT}/references/companion-voice.md`.

---

## Privacy Guard (mandatory, top-of-mind)

This skill reads session transcripts. **The hard rule, applied at every step: if session content reads as personal, skip it — analyse only engineering surfaces** (tool calls, file diffs, CI logs, PR comments, commit messages). Full skip/safe lists: `${CLAUDE_PLUGIN_ROOT}/references/privacy-guard.md` — read it at boot. The `gh api` PR/CI source is intrinsically engineering-only; the transcript filter is the load-bearing part.

---

## Two-source Data Model

The skill reads two complementary sources. Neither is subordinate.

| Source | What it carries | Primacy |
|---|---|---|
| **Session transcript** — the main agent's working memory, or `~/.claude/projects/<repo-id>/<session-id>.jsonl` | What the agent *did*: skills run, tool calls, where the user corrected, where iteration loops happened, where the user fixed it for the agent | Primary when no Compact happened — agent already has it in head. After a Compact: re-read the jsonl. |
| **GitHub PR + CI history** — via `gh api` | What failed *outside* the agent: CI checks, review threads, the commits that fixed them, cycle count, reviewer comments | Read when `gh` is available and authenticated (`gh auth status`). Without GitHub/authenticated `gh`, skip this source — transcript + local `git log` becomes the sole data source. |

The two combine: transcript says *"the agent forgot X"*, PR/CI says *"and CI then caught it after Y min"*. The lesson is the intersection.

Third source, opt-in via `--scan N` (default 0): **`docs/retros/*` historical** — surfaces recurring patterns across past retros, so a pattern that shows up for the third time gets promoted from a one-line patch to a structural fix.

---

## How This Skill Is Used

**Prompt-driven by default; `--auto` short-circuits the per-item ask.** Some example invocations:

- `/we:retro` — full pass on the current branch + last merged PR on it
- `/we:retro --pr 1998` — specific PR (open or merged)
- `/we:retro --scan 5` — full pass *and* read the last 5 entries in `docs/retros/` for patterns
- `/we:retro --pr 1998 --scan 10` — combine
- `/we:retro --auto` — apply every proposal immediately instead of gating each one on `[y/n]`,
  except the cases that still need a human call (see "Auto Mode" below). Combine with `--pr`/`--scan` as usual.

### Auto Mode (`--auto`)

Same pipeline (R1–R9), same rendered report (Step R5) printed **before** anything is applied — the
user always sees the wins/pain/proposals list, they just aren't asked per item. `--auto` changes
only Step R6's gate:

- **Auto-applied without asking:** any proposal targeting the **user's own repo** that is neither
  a plugin-repo edit nor a contract change (see below). These are the routine cases — a new
  path-filtered rule, a CLAUDE.md one-liner, a doc-only note.
- **Still asks, even under `--auto`** (this is "only when truly necessary"):
  - **Plugin-repo proposals** — ships to *every* plugin user; always confirm explicitly, same as
    non-auto mode.
  - **Contract-changing proposals** — a proposal that changes a schema, an MCP tool signature, a
    config-key name/shape, or any other public interface. High blast radius, expensive to get
    wrong from a wrong guess — confirm once, then apply.
  - **Genuinely ambiguous placement** — when Step R4's placement priority order doesn't clearly
    resolve (two reasonable homes, no obvious "more specific" pick) — ask once, then proceed with
    the answer for the rest of the run.
- Everything else is applied immediately and logged with `auto_applied: true` instead of
  "accepted by user" (Step R8's frontmatter/decisions section reflects this per item).
- `--auto` never skips Step R7's PR-vs-direct-commit policy — non-direct-commit repos and the
  plugin repo still go through a branch + PR; "auto" means auto-*decided*, not auto-*merged*.

The skill never silent-fires: the Step R5 report always prints before any edit lands. Outside
`--auto`, every applied edit also passes through a per-item `[y/n/edit-path/skip-for-later]` gate;
under `--auto`, that gate is skipped for routine same-repo non-contract proposals and kept for the
three exceptions above.

---

## Boot Protocol (every invocation)

Before producing any output, gather the landscape fresh.

**Always read:**

1. **Privacy guard reminder** — silently re-state to yourself: *if reads as personal, skip; engineering surfaces only*. This stays mandatory through every later step.

2. **Source scope** — determine what to analyse:
   - `git branch --show-current` — current branch
   - Detect default base branch: `git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||'` with `main` as fallback
   - Check GitHub availability: `gh auth status 2>/dev/null && HAS_GH=1 || HAS_GH=0`
   - If `HAS_GH=1`: `gh pr list --head $(git branch --show-current) --json number,state,title -L 1` — open PR for this branch; `gh pr list --base <base-branch> --state merged -L 5 --json number,mergedAt,headRefName,title` — recent merges
   - If `HAS_GH=0`: skip `gh pr` queries; retro runs from transcript + local `git log` only (see Step R2 below for the reduced-source path)
   - If `--pr <N>` was given: use it (requires `HAS_GH=1`; warn and fall back to transcript-only if not)
   - If nothing: ask the user *"which PR or branch should I scan? Default: last merged PR on `<current-branch>`."* — `[y/n/specify]`

3. **Rules + skills + docs landscape (user repo)** — frontmatter + first 10 lines only:
   - `.claude/rules/**/*.md` — to know which rules exist (for placement decisions later)
   - `CLAUDE.md` files at root + any sub-area (`apps/*/CLAUDE.md`) — to know what's always-loaded
   - `${CLAUDE_PLUGIN_ROOT}/skills/` — frontmatter `description:` of each skill (for cases where a fix belongs in the plugin)
   - Don't load full contents — that's thousands of tokens.

4. **Method grounding (how we work)** — read [`docs/concepts/how-we-work.md`](../../../docs/concepts/how-we-work.md), the canonical index, and the compact sections it points to (the altitudes, the pipeline, the skill catalog). This is the **same** manifest `/we:retro` loads — it grounds the improvement scan in the *current* APO method, so a friction is placed against how the pipeline is actually meant to work, not just the session diff. Indexed *sections* only, not full skill bodies. **If the manifest is absent in this repo** (most repos), note it once and ground from the plugin skill/agent descriptions instead — do not degrade silently.

5. **Historical retros (if `--scan N`)**:
   - `ls docs/retros/ 2>/dev/null | sort -r | head -N` — last N retros
   - Read each (they're small, structured) — note recurring themes

6. **Companion identity** (if configured): materialize per `${CLAUDE_PLUGIN_ROOT}/references/companion-voice.md`.

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
- **Commit chain:** `git log --oneline <base-branch>..<head-ref>` — the cycle visible as commits (always available)
- **If `HAS_GH=1` (GitHub + authenticated `gh` available):**
  - **PR overview:** `gh pr view <N> --json number,state,mergedAt,title,headRefName,baseRefName,reviews,comments,statusCheckRollup,commits`
  - **PR checks:** `gh pr checks <N>` — see which check runs flipped red across cycles
  - **Failed check logs (only red ones, tail):** for each failed check run, `gh run view <run-id> --log` and tail to the failure block (don't pull full logs)
- **If `HAS_GH=0` (no GitHub/gh):** skip the `gh` calls above. The PR/CI source is absent — note this in the report: *"No GitHub access — PR/CI data unavailable; analysis is transcript + commit log only."* Local quality gates (ruff, mypy, markdownlint, test output visible in transcript) substitute for CI evidence.
- **Historical retros if `--scan`:** read the N most recent under `docs/retros/`

### Step R3 — Triage findings

For each friction surfaced, classify by surface:

| Surface | Friction looks like |
|---|---|
| `CI / static` | ruff / mypy / eslint / tsc / markdownlint flipped red, pushed a fix-commit |
| `CI / tests` | test failed on CI but not locally (env gap), or wasn't run locally |
| `CI / build` | docker / EAS / native build broke after a tag push |
| `Review / AI reviewer` | CRITICAL or MAJOR thread blocked merge; the fix was small but not pre-empted |
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

**Contract changes ship their doc update in the same proposal.** If a proposal changes a
contract — a schema, an MCP tool signature, a config-key name/shape, a public skill invocation
surface — the diff preview includes the matching doc update (README, architecture doc,
reference file) alongside the code/config change, in the same proposal. Never split a contract
change and its doc update into separate proposals, and never leave the doc for "later." Tag such
a proposal `[contract]` in the report so Step R6 knows to always confirm it, even under `--auto`.

### Step R5 — Render the report

Four sections, in this order — and always **before** anything is applied:

```text
RETRO — PR #<n> (<branch>, merged <date>)
        session: <id>  ·  --scan <n>

WINS — keep doing
  · [memo] <what worked, and why it worked — no proposal attached>

PAIN — what cost time this cycle
  · <duration>: <what happened>
       └ evidence: <transcript turns, commit range, or check timestamps>
       └ root: <the actual cause, not the symptom>
       └ root²: <the cause behind that, when there is one>

PROPOSALS — concrete file changes
  · [P1 / 5min] NEW  .claude/rules/<category>/<topic>.md
                ───  <one-line summary of the rule>
                Default placement: <user repo | plugin — flagged>
                Diff preview: <the actual lines, frontmatter included>
                [y/n/edit-path/skip-for-later]

PATTERN HIGHLIGHTS (--scan only)
  · <n> of last <N> retros flag <theme> → structural-fix candidate: <what>

SUMMARY
  · <n> proposals, ~<n>min of edits · est. CI minutes saved next cycle
  · Log target: docs/retros/<date>-<topic>.md
```

Two things make this report worth reading rather than skimming: **every PAIN entry carries its
evidence** (a duration and a citation, not "CI was slow"), and **every proposal carries a real diff**
the user can approve without opening the file.

### Step R6 — Per-item gate

For each proposal in order, present and wait. Accepted tokens:

- `y` → apply, move to next
- `n` → skip permanently (record in log as "rejected by user")
- `edit-path: <new path>` → apply with redirected placement (e.g. user wants CLAUDE.md instead of rules/)
- `edit-content: ...` → user wants different wording; offer revised draft, re-ask
- `skip-for-later` → leave in log as "deferred", don't apply now
- `stop` → halt the gate, apply nothing further, jump to Step R8 (log)

⛔ Never apply silently. Every Edit/Write call follows an explicit `y` for that item.

**Under `--auto`:** skip the wait and answer `y` automatically for every proposal — except the
three cases in "Auto Mode" (`--auto`) above, which still stop and ask. That section is the
single spec of the exceptions.

### Step R7 — Apply approved items

For each `y`'d proposal:

- **In the user repo:**
  - If repo is configured for direct-commit (e.g. `plugin` repos with standing auth): Edit/Write on `main` directly.
  - Otherwise (default): create branch `retro/YYYY-MM-DD-<short-topic>`, apply Edit/Write, then:
    - If `HAS_GH=1`: open PR via `gh pr create` with the full retro report as PR body. User merges via normal flow.
    - If `HAS_GH=0`: commit directly to the branch and print: *"No GitHub access — push `retro/YYYY-MM-DD-<short-topic>` manually and open a PR when ready."*
- **In the plugin repo:** always PR (plugin is public).

After each apply, confirm in one short line: `applied · .claude/rules/quality/html-script-validation.md (NEW, 12 lines)`.

### Step R8 — Write the retro log

Regardless of how many proposals applied (zero is fine), write the log:

`<user-repo>/docs/retros/YYYY-MM-DD-<short-topic>.md`

With structured frontmatter:

```markdown
---
type: retro
pr: 1998
branch: feat/apo-refactor-phase-4
analysed_at: 2026-05-17T22:30:00Z
ci_cycles: 4
session_id: <id>
scan_window: 5
auto_mode: false
proposals_total: 3
proposals_accepted: 2
proposals_auto_applied: 0
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

- **Don't apply silently.** Every Edit follows an explicit `y` for that item; the Step R5
  report always prints before anything lands. `--auto` semantics + its three still-ask
  exceptions: "Auto Mode" section (the single spec).
- **Don't quote personal content** from the transcript — engineering surfaces only. Privacy guard, every step.
- **Don't modify source code.** Retros change MDs only. Code-level lessons (e.g. "this function had a race condition") flow back through the build if needed — retro proposes the rule, not the code fix.
- **Don't open the PR before applying the file changes.** Branch → apply → PR — in that order, so the PR body can reference the actual diff.
- **Don't auto-create tickets.** Skill can scaffold a Jira/GitHub issue stub only on explicit user request (`--ticket` flag, off by default).
- **Don't analyse cross-repo merges in one pass.** One PR per invocation; multi-PR retrospection is a future enhancement.
- **Don't push to protected repos directly** — repos without standing direct-commit auth always go through PR (rules and CLAUDE.md edits need human review).

---
