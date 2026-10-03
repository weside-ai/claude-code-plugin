---
name: optimize
description: >
  Decides optimization-inbox candidates with evidence, applies the approved ones, keeps the ledger.
  Triggers: "/we:optimize".
---

# /we:optimize

1. Act only on what the store says, read from the default branch: the shared checkout often lags,
   and where memory disagrees, the files win. Store format: `${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md`.
2. No change without evidence and the user's approval. Evidence is a measured number, or a
   repository fact (a contradicted claim, a gate violation, a documented limit). Every applied
   change carries a review date and is removed again when it does not pay off (step 4).
3. A product-owner decision (product, comfort, cost above a cap, deleting) is one question with a
   recommendation, never a ledger entry on its own.
4. Commits follow the target repo's own instruction files. Where they say nothing about where
   instruction changes land, ask once.
5. The plugin's own checkout holds no store. Plugin changes go there as a PR; their findings stay in this repo's inbox.

## 1 · Restore

```bash
git fetch -q origin && git show origin/<default>:.weside/optimization/CHARTER.md
```

Read the charter (goal, decisions, findings, next steps), then `LEDGER.md`, then every file in
`inbox/`, plus entries staged under `~/.claude/we-inbox/<repo>/` by an auto retro: move those into
`inbox/` now. No store → offer `/we:setup` § Instruction loop and stop. Tell the user briefly where
things stand, what you do now, and whether you need anything.

## 2 · Audit first?

Read `sources.lock`. Fetch and hash the sources per
`${CLAUDE_PLUGIN_ROOT}/references/instruction-sources.md` and compare; the lock itself stays the
audit's to write. Recommend `/we:instruction-audit` before deciding anything when a source hash
changed, the target model or effort differs from `.weside/config.json`, `claude --version` differs,
the audit is 30 days old or older, or no audit ran yet. One question; on "no", continue with the
inbox as it is.

## 3 · Consolidate

- Merge files that carry one key into the oldest; their evidence lines add up.
- Group by target file. Two entries on one file that pull in opposite directions are decided together.
- Order: evidence count × confidence (High 3, Medium 2, Low 1); `gap` and `G2-conflict` entries
  with a user correction among their evidence go first.

## 4 · Measure "after", sunset, ablation

- **After.** Ledger rows with an `after` still pending get their number now via the adapter, or
  without one from recurrence (store reference § Measurement adapter); a row
  that cannot be measured yet keeps `pending` and names when it can (a plugin change: after release
  and `/plugin update`). An `applied` row without `review_by` gets its date plus
  `optimization.review_days` (default 30), unless its change was a removal (`—`).
- **Sunset.** An `applied` row whose `review_by` has passed becomes a `remove` candidate
  (`source: sunset`) when its `after` shows no improvement over `before`, when its failure recurred
  after the apply date (an evidence line for its key), or when a gate now enforces the same thing.
- **Unmeasured.** A row past `review_by` whose failure never recurred and that nothing measures is
  no `remove` candidate: the change may be why the failure stopped. With an ablation command it goes
  to ablation first; without one it becomes a `flag` entry (`source: sunset`), deferred with the
  evidence line `- <date> deferred: unmeasurable, recommend keep`, for the user to decide with
  "keep" as the recommendation.
- **Ablation.** Of the `applied` instruction changes past `review_by` that sunset did not pick, two
  per run, the unmeasured ones first, then the oldest, go through the adapter's ablation command
  (the change reverted in a bench copy, probes run); no difference → a `remove` candidate
  (`source: ablation`). No adapter or no ablation command → skip it and say so in one line.
- Keys, the row a removal retires, and what a rejection moves:
  `${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md` § Ledger row. Order them into the step-3
  list with one evidence line each, confidence Medium.

## 5 · Decide

Per candidate, top down, until the user stops or the inbox is empty:

- **Admission.** A candidate that adds or rewords instruction text is proposed for apply only when
  all four hold; otherwise recommend reject or defer, and name the condition that failed:
  1. it names the observed failure;
  2. the failure occurred at least twice (evidence lines), once in a high-damage area (money,
     security, data loss), or it is a repository fact (a contradicted claim, a gate violation);
  3. when the failure recurred while an instruction on the topic stood, the remedy is a gate, a
     hook or a deletion, not a second wording
     (`${CLAUDE_PLUGIN_ROOT}/references/instruction-authoring.md` § What earns a line); a model-fit
     rewrite of a line that did not fail is not such a case;
  4. it states the expected effect, the metric that will show it, and the `review_by` date. The
     adapter in `.weside/optimization/measure/README.md` gives the before number, or without one
     the recurrence metric (store reference § Measurement adapter); a correction
     toward a contradicted repo fact uses the re-check of that fact as its metric. No metric →
     defer or reject, never apply.

  A `remove` candidate needs only the reason. A plugin skill is measured with `claude plugin eval`
  (or the `skill-creator` plugin's evals); a skill nobody invokes shows up in `/skill-doctor`.
- **Proposal.** The exact lines (NEW or EDIT) against `${CLAUDE_PLUGIN_ROOT}/references/instruction-authoring.md`,
  the number of lines it adds to always-loaded context (rules without `paths:`, `AGENTS.md`,
  `CLAUDE.md`), and the gate result after the edit.
- **Batch the questions** with `AskUserQuestion`, two to four candidates per call, each with
  apply · reject · defer, the recommendation first and marked "(Recommended)".

## 6 · Apply

- **This repo:** edit in a worktree, run the gate
  (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check-instruction-budget.py`), commit per the repo's rules.
- **A sibling repo** from `workspace`: offer it; on yes, `/we:sideload` (editing mode) with the
  approved proposal as the brief.
- **The plugin** (`target_repo: plugin`): with a local checkout, a native session there opens a PR,
  audited via `/doctor prompt-audit <path>`, and the ledger row's `after` waits for the release.
  Without a checkout, report the finding with its evidence; filing an upstream issue is the user's call.

## 7 · Write back

Before the turn ends, each fact once:

- every decided candidate → a `LEDGER.md` row per the store's § Ledger row, and its inbox file
  deleted in the same commit;
  a deferred one keeps its file with a `deferred:` evidence line;
- a new decision → replace the charter's line on that topic, old wording in parentheses
  ("replaces <date>: …");
- a changed finding → replace its row; next steps updated; `last_optimize:` set to today;
- the charter stays within 200 lines.

Commit per `${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md` § Layout (where store commits land). Close with one line: candidates applied /
rejected / deferred, inbox left, the next step. Then offer each `workspace` repo whose inbox is not
empty.
