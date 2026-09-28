---
name: retro
description: >
  Retrospective on a session or PR cycle: frictions from transcript + gh, scored against the repo's
  optimization charter when one exists (→ its ledger), else gated rule proposals. Triggers:
  "/we:retro", "retro", "post-mortem".
---

# /we:retro

1. Apply `${CLAUDE_PLUGIN_ROOT}/references/privacy-guard.md` at every step that reads the transcript.
2. Charter present (`.weside/optimization/CHARTER.md`, or the one the instruction files name) →
   **charter mode**: findings are scored against its objective and go to its ledger, never
   straight into rules. No charter → **rules mode**: gated proposals for rules and instruction files.
3. Measure what earlier accepted proposals did before proposing new ones.
4. Change Markdown only, never source code. Create no ticket unless the user asks.

Invocation: `/we:retro` (this branch and its last PR) · `--pr <N>` · `--scan <N>` (widen the history
window from 3) · `--auto` (rules mode: skip the per-item gate for routine proposals).

## Gather (parallel)

- The transcript: in context, or after a compaction `~/.claude/projects/<repo-id>/<session>.jsonl`,
  scoped to this cycle. Look for user corrections, nudges ("weiter", "go on"), stops that
  announced instead of acting, avoidable questions, loops on one problem, false "green" reports.
- With authenticated `gh`: `gh pr view <N> --json commits,reviews,comments,statusCheckRollup`,
  `gh pr checks <N>`, the failing part of each red run (`gh run view <id> --log-failed`). Without
  `gh`: `git log --oneline origin/<default>..HEAD` and say that PR/CI data is missing.
- History: charter mode reads the charter's findings and ledger; rules mode reads the newest 3 (or
  N) files in `docs/retros/` and every proposal they accepted.
- Placement landscape: frontmatter and first lines of `.claude/rules/**` and the instruction files.

## Measure earlier proposals

Per accepted proposal in the history window: **worked** (the metric moved; name before and after) ·
**did not work** (a PAIN finding of this retro) · **not yet measurable** (name what will measure it
and when). A file that landed is not an effect. A proposal that nothing can measure is itself a
finding: make it measurable.

## Findings

Each friction: what happened, the evidence (duration, transcript turn, commit range or run id), the
root cause, and the cause behind it when there is one. A friction with no Markdown remedy goes to
WINS if its fix was good, else it is dropped.

## Charter mode

1. Read the charter in the order its re-entry block gives (usually north star, decisions, current
   findings, next steps, then the ledger). Run a KPI command only if the charter names one. Act
   only on what these files say; where memory disagrees, the files win.
2. Score each finding against the charter's objective function and its constraints, in the
   charter's own order of priority. A finding that moves nothing
   the objective measures is dropped with one line.
3. Write back before the turn ends, each fact in one place:
   - a finding about a file in scope → an entry in the charter's ledger (class, decision, reason,
     evidence), or a replacement of the finding it supersedes;
   - a finding that needs work → a line under the charter's next steps;
   - a current finding changed → replace its row and keep the old version in parentheses
     ("replaces <date>: …"); never append a second row on the same topic;
   - every event also as a dated line in the charter's log, when it keeps one;
   - keep the charter within its own length cap.
4. A decision that belongs to the product owner (product, comfort, cost above a cap, deleting) is
   one question with a recommendation, not a ledger entry.
5. Commit per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md`.

## Rules mode

Per finding, one or two proposals: target file (path-bound rule > always-loaded instruction file >
`docs/` > plugin file, which ships to every user and is flagged), NEW or EDIT with the exact lines,
effort (`2min` … `30min`), priority P1 (recurring or costly) · P2 · P3. A proposal that changes a
contract (schema, tool signature, config key, skill invocation) carries its doc update and is
tagged `[contract]`.

Print the report before applying anything: WINS · EFFECT · PAIN · PROPOSALS · PATTERNS (a theme in
several retros is a structural-fix candidate) · SUMMARY. Then gate each proposal: `y` · `n` ·
`edit-path: <p>` · `skip-for-later` · `stop`. Under `--auto`, routine same-repo proposals apply
without the gate; plugin-repo proposals, `[contract]` proposals and an unclear placement still ask.

Apply the accepted ones per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` (the repo decides between a direct docs commit and a branch
with a PR; a plugin repo always gets a PR).

## Log (both modes)

Write `docs/retros/YYYY-MM-DD-<topic>.md` even with zero proposals. Frontmatter: `type: retro`,
`pr`, `branch`, `analysed_at`, `ci_cycles`, `mode` (charter|rules), `proposals_total`,
`proposals_accepted`, `applied_files`, `effects_measured` (proposal · from_retro · verdict · before ·
after · measured_by). Body: the report plus which items were accepted, deferred or rejected. In
charter mode the log points at the ledger entries instead of repeating them.

Close with one line: proposals applied or ledger entries written, the effect verdicts, the log path.
