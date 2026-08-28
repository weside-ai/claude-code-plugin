---
type: simulation-report
chunk: gates
scenario: D — mixed-authorship wave
round: 2
grade: 3
---
# Round 2 · Scenario D

Same wave: four chunks on `feat/TICKET-101-integration` — two by headless Codex workers, one by a
Claude `sonnet` worker, one committed by the Lead after a worker died without pushing. Receipt
complete. I re-run cold from the parallel-quality-gates step, then re-judge round 1.

Scope note: the four revised files are `we/agents/ac-reviewer.md`, `we/agents/pr-creator.md`,
`we/quality/dod.md`, `we/hooks/verification_gate.py`. `we/references/*.md` and
`we/skills/*/SKILL.md` were not in the chunk's file list — a defect there is a FORK.

## Verdict on round 1

| # | Round-1 finding | Verdict | Evidence (quoted revised line + file:line) |
|---|---|---|---|
| D1 | `/code-review` has no defined pass criterion, so `review_passed` is written by hand | **STILL OPEN — IN-SCOPE** | Both in-scope files name the gate and neither defines "clean": `dod.md:76` "- [ ] Bug-hunt passed (`review_passed` checkpoint — Codex adversarial-review or Claude's native `/code-review`)"; `pr-creator.md:16` "\| `review_passed` \| the Lead, after the one bug-hunt pass \| Yes \|". The Codex-only mapping is untouched at `integration-pipeline.md:102-104` (FORK half) |
| D2 | Blocking checkpoint set contradicts itself: three vs four | **STILL OPEN — FORK** | `pr-creator.md:11-18` still four rows under "## Prerequisites (BLOCKING)"; `integration-pipeline.md:154` still "**Blocking:** `review_passed`, `static_analysis_passed` and `test_passed` must all exist." The fix line is out of the chunk |
| D3 | `pr-creator` cannot tell a real gate from a typed checkpoint | **PARTIALLY — IN-SCOPE** | Provenance is now honest (D7), but Step 2 is unchanged: `pr-creator.md:31` `story status $TICKET`, `:34` "**If ANY checkpoint is missing → STOP. Tell the user which gates to run first.**" Still no verdict, author or evidence field; `story_checkpoint()` still takes any `STORY_PHASES` name |
| D4 | `integration-pipeline.md` restates the matrix in a form that answers D wrong | **STILL OPEN — FORK** | `integration-pipeline.md:100` unchanged: "(Claude wrote + Codex configured → `/codex:adversarial-review`; otherwise Claude's native `/code-review`)". `setup/SKILL.md:176` likewise |
| D5 | Parallel-gates instruction cannot be executed for the `/code-review` branch | **STILL OPEN — FORK** | `integration-pipeline.md:93` "Launch all three in **one message** so they run concurrently:" with `:97` "**one bug-hunt engine** → `review_passed`", against `:170` "**Never `Skill(skill=\"ci-review\")`**" |
| D6 | No DoD row catches a chunk whose phase files never changed | **FIXED (with a gap — see New 1)** | `dod.md:18` "- [ ] **Every planned phase landed** — each plan `### Phase` block's `**Files:**` actually changed in this diff"; `ac-reviewer.md:53-54` "- **Every planned phase landed?** … A phase that produced nothing is a Fail, whoever committed it."; output row `ac-reviewer.md:92` "\| Every planned phase landed \| Pass/Fail \| Each plan phase's `**Files:**` changed in this diff \|" |
| D7 | `pr-creator`'s table asserts a provenance nothing implements | **FIXED** | `pr-creator.md:15-16` "\| `ac_verified` \| the Lead, after the AC + DoD gate **and** the verification receipt exists \| Yes \|" / "\| `review_passed` \| the Lead, after the one bug-hunt pass \| Yes \|" — now agrees with `integration-pipeline.md:31-32` |
| D8 | `review.cross` documented as governing the bug-hunt and as not; `tools.codex` key absent from config | **STILL OPEN — FORK** | `worker-dispatch.md:79-81` and `:90` unchanged |
| D9 | Per-chunk AC-check required of workers that cannot run it; artefact is branch-keyed | **STILL OPEN — FORK (one half IN-SCOPE)** | `worker-dispatch.md:57` unchanged; `ac-reviewer.md:44` still "Look for an earlier review for this branch under `.reviews/`" and `:62` still keys the file on `<branch>`, so the chunk-branch reviews stay invisible at integration |
| D10 | `pr-creator` told to copy a block it is never told where to find | **FIXED** | `pr-creator.md:68` "the `## Verification` block **copied verbatim from `docs/plans/${TICKET}-story.md` § Verification**", plus `:70-73` "**Never author that block here.** You did not run the verification, so you cannot testify to it. No block in the plan → the verification step did not happen: stop, report that, and let the Lead run it." |

Cuttable lines from round 1:

| # | Line | Verdict |
|---|---|---|
| 1 | `pr-creator` `## Rules` step-paraphrase block | **FIXED** — two bullets remain (`:102-105`), neither restates a Step |
| 2 | ac-reviewer "review the diff, not entire files" twice | **FIXED** — only `ac-reviewer.md:40` "**Review the DIFF, not entire files.**" |
| 3 | ac-reviewer "ALWAYS save to file" twice | **FIXED** — only `ac-reviewer.md:64` "Save the file before you output the verdict." |
| 4 | ac-reviewer "not your job: bug-hunting" twice | **FIXED** — only `ac-reviewer.md:10` "This agent never hunts bugs" |
| 5 | ac-reviewer's "if available … otherwise apply the four criteria" fallback | **FIXED** — `ac-reviewer.md:55` "every applicable row of `${CLAUDE_PLUGIN_ROOT}/quality/dod.md`", no fallback copy |
| 6 | pr-creator explaining why a branch prefix is regex-extractable | **FIXED** — `pr-creator.md:26` "Keep the branch as `$BRANCH` and the key it carries as `$TICKET`" |
| 7 | `dod.md` closing restatement of `:3` + `:118` | **FIXED** — file ends at `:137` |
| 8 | The three "Not applicable → skip" bullets | **PARTIALLY** — standalone bullets gone, but `dod.md:29` "No such convention → skip." and `:46` "Verify each item that applies; skip the rest." remain |
| 9 | "Every AC gets its own row" duplicated | **FIXED** — absorbed into `ac-reviewer.md:50` "and each AC gets its own row" |
| 10 | `dod.md` § Review Output Format, a vaguer second copy | **FIXED as a cut, BROKEN as a citation** — replaced by `dod.md:135` "…fills a row per applicable item above; its output format lives in `agents/ac-reviewer.md`." See New 3 |

## Duplications, re-checked

| Rule | Owner now | Citations | Verdict |
|---|---|---|---|
| Bug-hunt engine matrix | `worker-dispatch.md:88-95` | `ac-reviewer.md:10-11` "that is the separate bug-hunt pass ([`worker-dispatch.md`](../references/worker-dispatch.md) § Bug-hunt dispatch)" ✓ · `dod.md:136-137` "`worker-dispatch.md` § Bug-hunt dispatch" ✓ · `integration-pipeline.md:100` and `setup/SKILL.md:176` still restate it lossily | **PARTIALLY** — both in-scope copies became citations; the two wrong copies are FORKs |
| Blocking checkpoint set | contested | `pr-creator.md:13-18` (4) · `dod.md:75-78` (4) · `integration-pipeline.md:154` (3) | **PARTIALLY** — the *writer* column no longer contradicts, the *count* still does |
| A DoD Fail blocks like an unmet AC | **now exists**: `dod.md:122-123` "A DoD row that Fails blocks exactly like an unmet acceptance criterion — there is no second, softer tier for \"only\" the DoD." | `ac-reviewer.md:68` is the verdict mechanism, legitimate; `integration-pipeline.md:66` still a verbatim restatement | **FIXED (owner)** / one FORK copy left |
| `.weside/dod.md` is additive, never a replacement | `dod.md:5` | `ac-reviewer.md:57-58` restates it: "The repo file is **additive and mandatory when it is there**, never a replacement" · `integration-pipeline.md:65-66` restates it | **STILL OPEN** — three statements, no citation |
| Horizontal scalability / `SCALABILITY-EXEMPT` | `dod.md:59-62` | `ac-reviewer.md:98` is a table row only | **FIXED** |
| Deliberate bypasses + register regeneration | `dod.md:26-29` | `ac-reviewer.md:97` row ✓ · `pr-creator.md:45-47` restates the action · `integration-pipeline.md:149-150` restates it again | **PARTIALLY** — see New 4 |
| Each AC verified individually with evidence | `dod.md:14` | `ac-reviewer.md:49-51` restates and *grew* ("no item passes without a citation") · `integration-pipeline.md:59-60` | **STILL OPEN** |
| Feature reachable / end-to-end | `dod.md:15-16` | `ac-reviewer.md:52` "- **Feature reachable?** User can navigate to the feature. **End-to-end?** The complete flow works." · `verification.md:27` · `<repo>/.weside/dod.md` | **STILL OPEN** |
| Verification receipt: oracle ladder + block | `verification.md:22-46` | `dod.md:33` cites it ✓ · `ac-reviewer.md:16-20` restates the rule with no path · `verification_gate.py:62-71` is deny-time output (exempt) · `integration-pipeline.md:75-89` | **PARTIALLY** |
| Never move to Done / the human merges | `dod.md:116` | `pr-creator.md:83` (transition) and `:105` (merge) — two distinct actions, acceptable · `integration-pipeline.md:198` · `orchestrate/SKILL.md:445-447` | **PARTIALLY** |
| Checkpoint list + who writes each | `integration-pipeline.md:26-37` | `pr-creator.md:13-18` restates four rows — now *consistent*, still a restatement · `dod.md:75-78` restates four | **PARTIALLY** |
| **Every planned phase landed** | contested — `dod.md:18` and `ac-reviewer.md:53-54` both *define* it, and already disagree | — | **NEW defect** — see New 1 |

Intra-file self-duplication (round 1's seven rows): **all FIXED.**

## Trace on the revised files

1. **Bug-hunt engine.** Unchanged by this revision: `worker-dispatch.md:93-95` — "Mixed authorship in one wave (a Codex chunk beside Claude chunks, or a tree the Lead committed for a dead worker) counts as \"anything else\": Claude's native `/code-review` over the whole integrated diff." Engine = `/code-review`; `orchestrate/SKILL.md:431-432` agrees; `integration-pipeline.md:100` and `setup/SKILL.md:176` still say the wrong thing for this wave (D4).
2. **AC + DoD gate, which now runs *before* the PR and *does* look at the fourth chunk.** `we:ac-reviewer` Step 1 (`ac-reviewer.md:30`) reads "the plan at `docs/plans/${TICKET}-story.md`" — so it holds the `### Phase` blocks — and Step 4 asks, unconditionally (the round-1 "(if available)" escape is gone):
   > "- **Every planned phase landed?** Each `### Phase` block's `**Files:**` in the plan actually changed in this diff. A phase that produced nothing is a Fail, whoever committed it." (`ac-reviewer.md:53-54`)

   and it now carries an output row that can fail the verdict — `ac-reviewer.md:92` "| Every planned phase landed | Pass/Fail | Each plan phase's `**Files:**` changed in this diff |", with `:68` "`<!-- VERDICT:BLOCKING -->` if any AC is unmet or any DoD row Fails". **Answer to brief question (1): yes — the fourth chunk finally meets a check before the PR, and it PASSES**, correctly: the Lead did commit it, the files did change. What made that chunk special — no worker, no report, no per-chunk AC-check — is caught by `dod.md:18`'s *second* clause, "a phase committed by someone other than its worker is named in the PR body with who did it and why", and that clause meets nothing anywhere (New 1).
3. **`review_passed`.** `/code-review` returns a findings list; no in-scope file says what clean looks like. I decide by hand again and write `story checkpoint TICKET-101 review_passed`. D1 stands, now inside a file the chunk owned.
4. **PR step.** `Agent(subagent_type="we:pr-creator", …)`. Step 2 runs `story status $TICKET` and `:34` says "If ANY checkpoint is missing → STOP". Read literally against the eleven names in `STORY_PHASES` (`orchestration.py:85-97`), `pr_created` and `ci_passed` are always missing at this point — the scoping word "4" that round 1 quoted was cut from the prose and now lives only in the table 20 lines above (Still-open 5).
5. **Step 3b (new).** "Run whatever pre-PR check scripts the repo ships … Regenerate any register the repo ships a generator for" (`pr-creator.md:44-47`) — in this wave nothing is armed, so it is a no-op; it duplicates `integration-pipeline.md:149-150` (New 4).
6. **Step 7 → the hook.** Body written to a file (`pr-creator.md:64` "Write the body to a file and pass it as `--body-file`"), `## Verification` copied verbatim from the plan. `verification_gate.py`: `_HEADING` matches, `_ORACLE` (`:46-49`) matches the receipt's single `**Oracle:** cli`, `_SEED` and `_ASSERTED` (`:59-60`) are filled → `_refusal` returns None. **Pass, and for a stronger reason than in round 1.**

**Which gate stops what, with which message**

| Gate | Stops | Message | Stops anything in D? |
|---|---|---|---|
| `verification_gate.py` | a body with no receipt, a template menu line, an unfilled receipt, or `--fill` | `:194` "This PR is opened with no body at all, so it claims work is done and says nothing about how that was observed." · `:200` "This PR claims work is done without saying how that was observed." · `:209` "This PR carries a `## Verification` heading over an unfilled receipt — the seed and the assertion are still the template's placeholders." | No — the receipt is real. Now genuinely harder to fool |
| `we:ac-reviewer` Step 6 | an unmet AC, or any Failing DoD row incl. **phase landing** | `<!-- VERDICT:BLOCKING -->` (`ac-reviewer.md:68`) | Would stop a *vanished* phase. Does not stop an *unattributed* one |
| `pr-creator` Step 2 | a checkpoint name absent from `story status` | `:34` "If ANY checkpoint is missing → STOP." | No. Four names exist; two are my own judgement |
| `dod.md` § Quality Gates | — | `:76` names the bug-hunt checkpoint | No — it names the gate, not its pass criterion |

**Answers:** engine = Claude's native `/code-review` (`worker-dispatch.md:93-95`); checkpoint = `review_passed`, still written on a criterion no file defines; `pr-creator` accepts it — it accepts any row with that name.

## Still open / new

1. **NEW — the rule the revision added is defined in two files, and the two definitions already disagree.** `dod.md:18`:
   > "- [ ] **Every planned phase landed** — each plan `### Phase` block's `**Files:**` actually changed in this diff; a phase committed by someone other than its worker is named in the PR body with who did it and why."

   `ac-reviewer.md:53-54`:
   > "- **Every planned phase landed?** Each `### Phase` block's `**Files:**` in the plan actually changed in this diff. A phase that produced nothing is a Fail, whoever committed it."

   The naming-in-the-PR-body clause is absent from the agent that fills the row, absent from the row's note (`ac-reviewer.md:92`), and absent from the body list `pr-creator.md:66-68` ("**Summary**, **Changes** (from the commits), **Test Plan**, the ticket key … and the `## Verification` block"). Two definitions, one behaviour, one already lost — exactly what `plugin-authoring.md:26-29` predicts. Concrete failure: Scenario D's fourth chunk passes the row and the PR names no one. Ordering makes a checkbox the wrong home anyway — `we:ac-reviewer` runs at the AC+DoD gate, before a PR body exists.
   *Smallest fix:* add to `pr-creator.md:66-68`'s body list "and, for any plan phase committed by someone other than its worker, one line naming who committed it and why"; cut the clause from `dod.md:18` back to the landing check so `ac-reviewer.md:53-54` is a faithful reading of it. **IN-SCOPE.**

2. **STILL OPEN (D1) — the gate this scenario always walks into has no pass criterion, in files the chunk owned.** `dod.md:76` and `pr-creator.md:16` (quoted above) both name `review_passed` and neither says what a clean `/code-review` is. Compare `ac-reviewer.md:68-69`, which defines its own verdict. Concrete failure: I wrote the blocking checkpoint on an unrecorded judgement and `pr-creator` could not have known.
   *Smallest fix:* `dod.md:76` → "- [ ] Bug-hunt passed (`review_passed`) — Codex `approve`, or `/code-review` returning zero BLOCKING/WARNING findings; the finding count goes in the checkpoint's `extra_data`." **IN-SCOPE** (the mirror at `integration-pipeline.md:102-104` is a FORK).

3. **NEW — `dod.md`'s replacement citation mis-describes the file it cites.** `dod.md:135`:
   > "`we:ac-reviewer` fills a row per applicable item above; its output format lives in `agents/ac-reviewer.md`."

   `ac-reviewer.md:88-100` is a fixed nine-row table plus repo rows. Nothing in it covers `dod.md:19` "Parallelisation considered", § Evidence (`:69-71`), the Documentation cascade (`:86-104`), Migrations (`:49-50`), timezone/range/string-length/index-order (`:53-56`). Same class as D7: a sentence asserting a behaviour nothing implements. Concrete failure: a reader trusts that every checked box got a row; a wave that skipped parallelisation or shipped a doc contradicting the code fails no row.
   *Smallest fix:* `dod.md:135` → "`we:ac-reviewer` fills the rows listed in `agents/ac-reviewer.md` § Output Format, plus one per `.weside/dod.md` item; the remaining boxes are the Lead's." **IN-SCOPE.**

4. **NEW — register regeneration now lives at two pipeline stages.** `pr-creator.md:45-47`:
   > "Regenerate any register the repo ships a generator for and confirm the committed copy matches — a stale generated file fails CI *after* the PR is open, which costs a full cycle."

   against `integration-pipeline.md:149-150` "If a bypass annotation changed and the repo ships `scripts/generate-bypass-register.sh`, regenerate the register into the same docs commit." — the docs step, which runs *before* `pr-creator`. Concrete failure: the regeneration lands in the docs commit, then `pr-creator` re-runs it and finds a clean tree, or re-runs it and produces an uncommitted diff it has no instruction to commit before `git push` at `:51`.
   *Smallest fix:* `pr-creator.md:45-47` keeps the *check* and drops the regeneration — "confirm any generated register matches its generator; a mismatch means the docs step was skipped, so stop and say so." **IN-SCOPE.**

5. **NEW (from a cut) — Step 2's scope word was removed with the `## Rules` block.** `pr-creator.md:34`:
   > "**If ANY checkpoint is missing → STOP. Tell the user which gates to run first.**"

   Round 1's `pr-creator.md:15` read "All 4 checkpoints must exist before PR creation"; that count now lives only in the Prerequisites table twenty lines above, while `story status` prints against eleven `STORY_PHASES` names (`orchestration.py:85-97`), two of which cannot exist yet. Scoping ambiguity, not a hard defect — the table is close and unambiguous.
   *Smallest fix:* "If any of the four Prerequisites checkpoints is missing → STOP." **IN-SCOPE.**

6. **STILL OPEN (D3) — Step 2 still verifies that four strings were typed.** Quoted above. `story_checkpoint()` takes any `STORY_PHASES` name from any shell; no verdict, author or evidence field. In this wave `ac_verified` and `review_passed` are both mine, one of them (item 2) on an undefined criterion. **IN-SCOPE** for `pr-creator.md`; the `--evidence` half is `orchestration.py`, a FORK.

7. **STILL OPEN (D9, in-scope half) — the per-chunk review artefact stays invisible at integration.** `ac-reviewer.md:44` "Look for an earlier review for this branch under `.reviews/`" against `:62` "Write to `.reviews/<YYYYMMDD-HHMM>_<branch>_V<n>.md`". The integration branch is `feat/TICKET-101-integration`; any chunk review sits under a chunk-branch name. An absent entry is still indistinguishable between `review.cross: false`, a Codex worker that structurally cannot run it, a dead worker, and a worker that ran it and passed.
   *Smallest fix:* `ac-reviewer.md:44` → "…for this branch **and for any branch merged into it** under `.reviews/`". **IN-SCOPE.**

8. **STILL OPEN — FORKS, unchanged and re-verified:** D2 (`integration-pipeline.md:154`), D4 (`integration-pipeline.md:100`, `setup/SKILL.md:176`), D5 (`integration-pipeline.md:93` vs `:170`), D8 (`worker-dispatch.md:79-81`, `:90`), D9's dispatch half (`worker-dispatch.md:57`).

## Judging the revision by its own standard

Line counts moved the right way — `ac-reviewer.md` 104 lines, `pr-creator.md` 105, `dod.md` 137 — and every cut removed a no-op rather than a rule. The best of them: `ac-reviewer.md:55` dropped the "otherwise apply the four criteria" fallback, which was a fifth copy of four DoD rows, and gained a hard requirement instead ("The repo file is **additive and mandatory when it is there**"); `pr-creator.md`'s `## Rules` went from six step-paraphrases to two invariants; `dod.md` § Review Output Format became one citing sentence.

**The hook exceeded round 1.** I filed no defect against it — round 1 called the two-regex shape its stated contract. The revision hardened it anyway: `_ORACLE` (`:46-49`) requires one *named* oracle and its `[^|\n]*$` tail rejects the template's own menu line (`**Oracle:** cli | ui | substitute | not-applicable`); `:204-211` blocks a heading over an unfilled `**Seed:**`/`**Asserted:**`; `:194` blocks a `--fill` create with no body. Three shapes that passed in round 1 now deny.

**One cut removed something I needed:** the word "4" from `pr-creator`'s stop condition (Still-open 5). Nothing else. The `dod.md:19` parallelisation item and § Evidence survived and remain unrowed, but that predates this round.

## Grade

**3** — real, verifiable in-scope repair: D6, D7 and D10 fixed outright, every intra-file duplication gone, the "a DoD Fail blocks" rule finally has an owner at `dod.md:122-123`, and the verification hook is stronger than the round that judged it sound. Held below 4 by the round-1 finding rated highest, D1, still standing in a file this chunk revised, and by two contradictions the revision itself introduced (a rule defined twice and already divergent; a citation that mis-describes its target). Held above 2 because the fourth chunk now meets a check that can fail the verdict, at a step that runs before the PR.
