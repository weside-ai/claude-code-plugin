---
name: optimize
description: >
  Decides optimization-inbox candidates with evidence, applies the approved ones, keeps the ledger.
  Triggers: "/we:optimize".
---

# /we:optimize

1. Act only on what the store says, read from the default branch: the shared checkout often lags,
   and where memory disagrees, the files win. Store format: `${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md`.
2. No change without evidence and the decider's yes, or a remove default the decider let stand one
   run (step 5): the HR role, which decides weekly (L0 §Changing this); without a crew, the user.
   Evidence is a measured number or a repository fact (a contradicted claim, a gate violation, a
   documented limit). Every applied change carries a review date and goes when it does not pay off.
3. A product-owner decision (product, comfort, cost above a cap, deleting) is one question with a
   recommendation, never a ledger entry on its own.
4. Commits follow the target repo's own instruction files. Where they say nothing about where
   instruction changes land, ask once.
5. The plugin's own checkout holds no store. Plugin changes go there as a PR; their findings stay in this repo's inbox.

## 1 · Close what settled itself, then restore

In the store's checkout, up to date with the default branch:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/optimization_close.py"
git fetch -q origin && git show origin/<default>:.weside/optimization/CHARTER.md
```

The script sets every inbox entry a merged PR names to `applied` and every unconfirmed old one to
`expired` (rules: store reference § Inbox entry, Lifecycle), writes their ledger rows and prints
them; its changes go into this run's store commit. Exit 2: relay the line and decide by hand.
Steps 3 to 5 decide only what is left.

Read the charter (goal, decisions, findings, next steps), then `LEDGER.md`, then every file in
`inbox/`, plus entries staged under `~/.claude/we-inbox/<repo>/` by an auto or collect retro: move each into
`inbox/` now with `retro_write.py inbox/ <file> --date <its file name's date>` (keeps the first-seen date, revives an expired key), then delete the staged file. With `feedback-sources.md`, add each listed repo's plugin findings as named
sources, read-only, key, target and fact only (`optimization-store.md` § Plugin checkout and workspace, Feedback sources). No
store → offer `/we:setup` § Instruction loop and stop. Tell the user briefly where
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
- Order: `remove` candidates first (retro entries and step 4), then evidence count × confidence
  (High 3, Medium 2, Low 1); `gap` and `G2-conflict` entries with a user correction lead the adds.
- **Pre-sort** (optional, the decider asks for it, or the inbox holds more than ten entries after
  consolidation): one read-only worker (`we:explore-medium`) gets the inbox and ledger paths and
  returns the ten adds it would decide first, each with one line why. Check each line at its
  entry; step 5 decides the removals and these ten, the rest stays in `inbox/` for the next run.
- **A rejected key again.** An entry whose key has a `rejected` ledger row goes on only when its new
  evidence answers that row's reason (the count adds the row's evidence: a second occurrence answers
  "seen once"). Otherwise delete the file in the store commit; the rejection stands.

## 4 · Delete first: after, sunset, ablation

- **After.** Ledger rows with an `after` still pending get their number now via the adapter, or
  without one from recurrence (store reference § Measurement adapter); a row
  that cannot be measured yet keeps `pending` and names when it can (a plugin change: after release
  and `/plugin update`); a missing `review_by` per store reference § Ledger row.
- **Sunset.** An `applied` row whose `review_by` has passed becomes a `remove` candidate
  (`source: sunset`) when its `after` shows no improvement over `before`, when its failure recurred
  after the apply date (an evidence line for its key), or when a gate now enforces the same thing.
- **Unproven.** An `applied` instruction-text row past `review_by` with no measured effect (no
  recurrence is no measurement) and no mandatory class (money, tenant isolation or authorization,
  data or deletion, secrets, release) is a `remove` candidate (`source: sunset`). It stays one more
  `review_days` only when the target file's owner (a role file: that role; else the decider) names
  in one sentence the damage it catches in prod or by mistake ("useful" is not enough).
- **Ablation.** Of the `applied` instruction changes past `review_by` that sunset did not pick, two
  per run, the oldest first, go through the adapter's ablation command (the change reverted in a
  bench copy, probes run): no difference → a `remove` candidate (`source: ablation`); none → say so.
- Keys, the row a removal retires, and what a rejection moves:
  `${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md` § Ledger row. They head the step-3
  list with one evidence line each, confidence Medium. Step 4 runs every run before step 5, also
  with a full inbox; a run that stops early stops after the removals.

## 5 · Decide

Per candidate, top down, until the decider stops or the inbox is empty. Every decided candidate ends
`applied` or `rejected`; nothing is put off, because a put-off entry comes back every run.

- **Only what lasts goes to the decider:** a gate, a hook, a script, a deletion, a fix of a contradicted
  repo fact, or instruction text that passes admission. Everything else is `rejected` with its
  reason, unasked.
- **Admission.** Instruction text added or reworded, a role's own file included, goes to the decider
  only when all four hold, else it is rejected with the failed condition. Replacing a line at least
  as long in the same file, of no mandatory class, lifts 2; the ledger reason names that line:
  1. it names the observed failure;
  2. the failure occurred at least twice (evidence lines), once in a mandatory class (step 4), or
     it is a repository fact (a contradicted claim, a gate violation);
  3. when the failure recurred while an instruction on the topic stood, the remedy is a gate, a
     hook or a deletion, not a second wording
     (`${CLAUDE_PLUGIN_ROOT}/references/instruction-authoring.md` § What earns a line); a model-fit
     rewrite of a line that did not fail is not such a case;
  4. it states the expected effect, the metric that will show it, and the `review_by` date. The
     adapter in `.weside/optimization/measure/README.md` gives the before number, or without one
     the recurrence metric (store reference § Measurement adapter); a correction
     toward a contradicted repo fact uses the re-check of that fact as its metric. No metric →
     reject.
- **Proposal.** The exact lines (NEW or EDIT) against `${CLAUDE_PLUGIN_ROOT}/references/instruction-authoring.md`,
  the lines it adds and removes in its target file, and the gate result after the edit.
- **Batch the questions** to the decider (rule 2), two to four candidates per batch, each one
  question line (L0 §Talking and the board): the change, its benefit in one sentence, your
  recommendation last. Chosen → applied; not chosen → `rejected` ("not chosen"); say so in it. A
  batch of `remove` candidates, each needing only its reason, is one question with the default
  "remove"; without an answer by the next run the default holds.

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
- a new decision → replace the charter's line on that topic, old wording in parentheses
  ("replaces <date>: …");
- a changed finding → replace its row; next steps updated; `last_optimize:` set to today;
- the charter stays within 200 lines.

Commit per `${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md` § Layout (where store commits land). Close with one line: candidates applied /
rejected, inbox left, step 4's rows read and remove candidates, lines +/− per target file and the
run's change of `all` in `check-instruction-budget.py --totals` (positive: name the removals that
offset it, or ask the decider once), the next step; then offer each `workspace` repo with an inbox.
