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
   repository fact (a contradicted claim, a gate violation, a documented limit).
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
`inbox/` now. No store → offer `/we:setup` § Instruction loop and stop. Tell the user in at most three
sentences where things stand, what you do now, and whether you need anything.

## 2 · Audit first?

Read `sources.lock` → `audit`. Recommend `/we:instruction-audit` before deciding anything when the
target model or effort differs from `.weside/config.json`, `claude --version` differs, the audit is
30 days old or older, or no audit ran yet. A changed source hash surfaces there too. One question;
on "no", continue with the inbox as it is.

## 3 · Consolidate

- Merge files that carry one key into the oldest; their evidence lines add up.
- Group by target file. Two entries on one file that pull in opposite directions are decided together.
- Order: evidence count × confidence (High 3, Medium 2, Low 1); `gap` and `G2-conflict` entries
  with a user correction among their evidence go first.

## 4 · Measure "after" for earlier changes

Ledger rows with an `after` still pending get their number now via the adapter; a row that cannot be
measured yet keeps `pending` and names when it can (a plugin change: after release and `/plugin update`).

## 5 · Decide

Per candidate, top down, until the user stops or the inbox is empty:

- **Evidence.** The repo's adapter in `.weside/optimization/measure/README.md` gives the
  before number; none → record `unmeasured`. A plugin skill is measured with `claude plugin eval`
  (or the `skill-creator` plugin's evals); a skill nobody invokes shows up in `/skill-doctor`.
  A High finding contradicted by the repo needs no number.
- **Proposal.** The exact lines (NEW or EDIT) against `${CLAUDE_PLUGIN_ROOT}/references/instruction-authoring.md`,
  and the gate result after the edit.
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

- every decided candidate → a `LEDGER.md` row, and its inbox file deleted in the same commit;
  a deferred one keeps its file with a `deferred:` evidence line;
- a new decision → replace the charter's line on that topic, old wording in parentheses
  ("replaces <date>: …");
- a changed finding → replace its row; next steps updated; `last_optimize:` set to today;
- the charter stays within 200 lines.

Commit per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md`. Close with one line: candidates applied /
rejected / deferred, inbox left, the next step. Then offer each `workspace` repo whose inbox is not
empty.
