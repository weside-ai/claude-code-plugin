---
type: simulation-report
chunk: gates
scenario: D — mixed-authorship wave
round: 1
grade: 2
---
# Round 1 · Scenario D

Wave: four chunks on `feat/TICKET-101-integration` — two by headless Codex workers, one by a
Claude `sonnet` worker, one committed by the Lead after a worker died without pushing. Receipt
complete. `review.cross: true`, `execution.default: "codex"`, `verification.required: true`.
I am the Lead, entering at the parallel-quality-gates step.

## Trace

1. **`Read we/references/integration-pipeline.md` § Quality gates** → three gates in one message,
   `static-analyzer`, `test-runner`, and *"one bug-hunt engine"*. Line 99 tells me the writer picks
   it and line 101 hands the matrix to `worker-dispatch.md`. I do not have the answer yet, so I
   read on.
2. **`worker-dispatch.md` § Bug-hunt dispatch (already loaded — I loaded it at dispatch time for
   the worker contract)** → the deciding line is `worker-dispatch.md:93-95`:
   > "Mixed authorship in one wave (a Codex chunk beside Claude chunks, or a tree the Lead committed
   > for a dead worker) counts as \"anything else\": Claude's native `/code-review` over the whole
   > integrated diff."
   Scenario D is the sentence's own worked example, twice over. **Engine: Claude's native
   `/code-review`.**
3. **Reachability check (the brief's question).** The decision does **not** require a reference I
   did not open. `orchestrate/SKILL.md:429-433` — my own skill, always in context — carries the
   same rule verbatim: *"any chunk from Codex, a foreign engine, or a tree the Lead committed for a
   dead worker → Claude's native `/code-review` over the whole diff"*. So two loaded sources agree.
   The hazard is the reverse: the two *lossy* copies (`integration-pipeline.md:100`,
   `setup/SKILL.md:175-177`) both omit the mixed case, and a Lead who read only
   `integration-pipeline.md` — the file that owns this step — would apply *"Claude wrote + Codex
   configured → `/codex:adversarial-review`"* to a wave that does contain a Claude chunk and does
   have Codex configured, and dispatch the **wrong** engine. See Defect 4.
4. **Note what row 1 keys on.** `worker-dispatch.md:90` requires `tools.codex: true`. The world's
   `.weside/config.json` has no `tools` block at all — it has `execution.default: "codex"`. Row 1
   therefore cannot match here on its own terms either; I reach `/code-review` by two independent
   routes but by different reasoning (Defect 8).
5. **Launch the three gates in one message.** `Agent(subagent_type="we:static-analyzer")`,
   `Agent(subagent_type="we:test-runner")`, and — for the bug-hunt — `Skill(skill="code-review")`.
   Here the instruction breaks: `/code-review` is a *skill*, not an agent, so it runs in **my**
   context, serially, and costs me the overview that this same file protects at line 169-171
   ("**Never `Skill(skill="ci-review")`** — that loads the skill into the main context and costs
   the Lead its overview"). I would silently substitute `Agent(subagent_type="general-purpose",
   model="opus", prompt="run /code-review over the merged diff …")` to keep the parallelism, and
   note that the pipeline never says to (Defect 5).
6. **Point the bug-hunt at the test anti-patterns**, per `worker-dispatch.md:97-100`. In this diff
   `tests/services/test_widget_summary.py` "asserts the summary string, mocks the chat model" — a
   candidate implementation-coupled/tautological finding. This is bug-hunt territory, correctly
   *not* `we:ac-reviewer`'s.
7. **Map the answer to `review_passed`.** `integration-pipeline.md:102-104` maps only the Codex
   answer: *"Codex answers with JSON rather than a marker — `approve` → write `review_passed`;
   `needs-attention` → fix, re-run, then write it. Skip that mapping and the blocking gate in
   `pr-creator` never gets set."* My engine is `/code-review`, which returns a findings list with
   **no verdict marker and no JSON**. Nothing in any of the four files under test says what a clean
   `/code-review` looks like. I would decide by hand — "no BLOCKING findings" — and write
   `python3 …/orchestration.py story checkpoint TICKET-101 review_passed`. That decision is mine,
   unrecorded and unfalsifiable (Defect 1, the worst thing here).
8. **Docs step**, then the PR step. `integration-pipeline.md:154` blocks on **three** checkpoints;
   `pr-creator.md:15` blocks on **four**. I hold all four, so the contradiction does not bite this
   run — it bites any run where `ac_verified` is the missing one (Defect 2).
9. **`Agent(subagent_type="we:pr-creator", prompt="Create PR for TICKET-101")`.** Playing
   `pr-creator`: Step 1 extracts `TICKET-101` from `feat/TICKET-101-integration`. Step 2, its
   entire verification step, is:
   > "```bash
   > python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story status $TICKET
   > ```
   > **If ANY checkpoint missing → STOP. Tell the user which gates to run first.**"
   `story_status()` (`we/scripts/orchestration.py:1302-1360`) returns `phase`, `branch`,
   `pr_number`, `test_coverage`, `files_modified`, `commits`, `extra_data`, `created_at` — a list of
   *names that were typed*. There is no verdict field, no author field, no evidence field, and
   `story_checkpoint()` accepts any name in `STORY_PHASES` from anyone with a shell. **`pr-creator`
   cannot tell a real gate from a checkpoint someone typed**, and nothing in its file asks it to
   (Defect 3).
10. **Who wrote each of the four in this wave.** Two are not mine: `we/agents/static-analyzer.md:56`
    and `we/agents/test-runner.md:61` each run `story checkpoint "$TICKET" <phase>` themselves, so
    `static_analysis_passed` and `test_passed` have a real writer with a stated condition
    (`static-analyzer.md:59` "**Only if ALL checks passed.**"). The other two are mine and only
    mine: nothing in `we/agents/` or `we/skills/` writes `ac_verified` or `review_passed` — the
    only occurrences of those two strings outside the pipeline table are in `pr-creator`'s own
    prerequisites table (`pr-creator.md:19-20`), which is the file *reading* them. `ac_verified` I
    wrote after a green AC table; `review_passed` I wrote on my own reading of `/code-review`
    (Defect 7).
11. **Steps 3–4:** rebase onto `main`, `git push -u origin feat/TICKET-101-integration
    --force-with-lease`. Step 7: `gh pr create --body-file <tmp>` with the `## Verification` block
    copied out of the plan. `verification_gate.py` `_HEADING` + `_ORACLE` both match — the hook
    passes. In Scenario D the hook is not the interesting gate; it is the only one here that
    inspects a shape rather than a name — and a shape is all it inspects.
12. **Step 8:** Jira comment + transition to In Review, soft-fail. **Step 9:** `story checkpoint
    TICKET-101 pr_created`. Back in `integration-pipeline.md` § One ci-review pass.

**Answer to the three questions the scenario asks:** engine = Claude's native `/code-review`,
decided by `worker-dispatch.md:93-95` (mirrored at `orchestrate/SKILL.md:429-433`); checkpoint =
`review_passed`, written by me on an undefined pass criterion; `pr-creator` accepts it — it accepts
any row with that name.

## Which gate stops what, with which message

| Gate | Stops | Message | Would it stop anything in Scenario D? |
|---|---|---|---|
| `verification_gate.py` (PreToolUse on `gh pr create`) | a PR body with no `## Verification` + no oracle word | *"This PR claims work is done without saying how that was observed."* | No — receipt is complete and copied. The only gate here that inspects a **shape** rather than a name — two regexes (`:28-32`), so a heading plus the bare word `Oracle:` passes with nothing under it. That is its stated contract (`:11` "Blocks on ABSENCE"), not a bug. |
| `pr-creator` Step 2 | a **name** absent from `story_checkpoints` | *"If ANY checkpoint missing → STOP"* (no wording given) | No. All four names exist. It never asks how they got there. |
| `we:ac-reviewer` Step 6 | an unmet AC or a Failed DoD row | `<!-- VERDICT:BLOCKING -->` | Not for authorship: nothing hands it who wrote which chunk, and its DoD Quick Check table has no row for phase landing, worker reports, or per-chunk review. |
| `worker-dispatch.md:108` | an **empty** worktree | *"A worker that reports success without commits or a dirty tree signals a lost dispatch."* | No. The dead worker's chunk is not empty — the Lead committed it. The tree changed; the report does not exist; nothing looks for a report. |
| `quality/dod.md` | — | — | **No row anywhere catches a chunk whose phase files never changed.** See Defect 6. |

**Per-chunk AC-check, and whether anyone can check it.** `worker-dispatch.md:57` requires it
(*"**AC-check own diff** (when `review.cross: true`)"*), and the mechanism lives in
`develop/SKILL.md:137-146` — a `/we:develop` step that runs `we:ac-reviewer` as a Claude Code
subagent. A headless Codex worker never runs `/we:develop` and, by `worker-dispatch.md:52-55`,
*"workers can't load references"* — it has no access to the plugin's agent registry at all. So for
the two Codex chunks the per-chunk pass is **structurally impossible**, and for the Lead-committed
chunk there was no worker to run it. Only the `sonnet` chunk could have.

Is any of it checkable? The only artefact is `.reviews/<YYYYMMDD-HHMM>_<branch>_V<n>.md`
(`ac-reviewer.md:73`), and it is keyed on **`<branch>`**. The integration run is on
`feat/TICKET-101-integration`; the chunk reviews, if any, sit under chunk-branch names. So
`ac-reviewer.md:39-41` — *"Look for an earlier review for this branch under `.reviews/`"* — finds
nothing even for the one chunk that did run it. An absent `.reviews/` entry is indistinguishable
between: `review.cross: false`, a Codex worker that cannot run it, a dead worker, and a worker that
ran it and passed. **`we:ac-reviewer` at integration neither knows nor cares**, and the Lead can
silently skip the whole rule with no artefact anywhere disagreeing.

## Duplications against the single-owner rule

Cross-file first — these are the expensive ones.

| Rule | file:line A | file:line B (and C, D) | Which should own it |
|---|---|---|---|
| **Bug-hunt engine matrix** (four copies, two lossy) | `we/references/worker-dispatch.md:88-95` | `we/references/integration-pipeline.md:99-101` · `we/agents/ac-reviewer.md:10-12` · `we/skills/orchestrate/SKILL.md:429-433` · `we/skills/setup/SKILL.md:175-177` | `worker-dispatch.md` § Bug-hunt dispatch; the other four cite one sentence + path |
| **Blocking checkpoint set before the PR** (and they disagree) | `we/references/integration-pipeline.md:154` (three) | `we/agents/pr-creator.md:15-22` (four) · `we/quality/dod.md:76-79` (four) | `pr-creator.md` § Prerequisites |
| **A DoD Fail blocks like an unmet AC** | `we/agents/ac-reviewer.md:120` | `we/references/integration-pipeline.md:66` | `quality/dod.md` § Issue Severity — which today (`dod.md:122-128`) does **not** say it, so the owner is empty and both copies are orphans |
| **`.weside/dod.md` is additive, never a replacement** | `we/quality/dod.md:5` | `we/agents/ac-reviewer.md:55-59` · `we/references/integration-pipeline.md:65-66` | `quality/dod.md:5` |
| **Horizontal scalability / `SCALABILITY-EXEMPT`** (full restatement incl. the shape list) | `we/quality/dod.md:59-62` | `we/agents/ac-reviewer.md:64-69` (+ output row `:106`) | `quality/dod.md` |
| **Deliberate-bypass compliance + register regeneration** | `we/quality/dod.md:25-28` | `we/agents/ac-reviewer.md:60-63` · `we/agents/pr-creator.md:46-52` | `quality/dod.md` |
| **Each AC verified individually with evidence** | `we/quality/dod.md:14` | `we/agents/ac-reviewer.md:46-47` · `we/agents/ac-reviewer.md:119` · `we/references/integration-pipeline.md:59-60` | `quality/dod.md:14` |
| **Feature reachable / end-to-end** | `we/quality/dod.md:15-16` | `we/agents/ac-reviewer.md:48-49` · `we/references/verification.md:27` · `<repo>/.weside/dod.md` "User-facing AC proves reachability" | `quality/dod.md:15-16` |
| **Verification receipt: oracle ladder + block required** | `we/references/verification.md:22-46` | `we/quality/dod.md:33-35` · `we/agents/ac-reviewer.md:17-20` · `we/references/integration-pipeline.md:75-89` | `references/verification.md` |
| **Never move the ticket to Done / the human merges** | `we/quality/dod.md:118` | `we/agents/pr-creator.md:80` · `we/agents/pr-creator.md:107` · `we/references/integration-pipeline.md:198` · `we/skills/orchestrate/SKILL.md:445-447` | `quality/dod.md:118` |
| **Checkpoint list + who writes each** | `we/references/integration-pipeline.md:26-37` | `we/scripts/orchestration.py:85-97` (comments restate it) · `we/agents/pr-creator.md:17-22` (restates four rows with a divergent "From" column — see Defect 7) | `integration-pipeline.md` table; the code comments and `pr-creator` cite it |

Intra-file self-duplication — cheaper to fix, still defects:

| Rule | file:line A | file:line B | Which should own it |
|---|---|---|---|
| Review the diff, not entire files | `we/agents/ac-reviewer.md:37` | `we/agents/ac-reviewer.md:118` | Step 2 (`:37`) |
| Always save the review to file first | `we/agents/ac-reviewer.md:71-74` | `we/agents/ac-reviewer.md:121` | Step 5 (`:71-74`) |
| Not your job: bug-hunting | `we/agents/ac-reviewer.md:10-12` | `we/agents/ac-reviewer.md:122` | The Purpose block (`:10-12`) |
| Verify all 4 checkpoints, stop if missing | `we/agents/pr-creator.md:15` | `we/agents/pr-creator.md:101` | Prerequisites (`:15`) |
| Rebase before pushing; save `pr_created` after | `we/agents/pr-creator.md:41-44`, `:84-88` | `we/agents/pr-creator.md:102` | The Steps |
| Transition → In Review, soft-fail | `we/agents/pr-creator.md:76-79` | `we/agents/pr-creator.md:103` | Step 8 (`:76-79`) |
| A story is DONE when both DoDs are met | `we/quality/dod.md:3-5` | `we/quality/dod.md:144-145` | The opening (`:3-5`) |

**Exempted, deliberately:** `we/hooks/verification_gate.py:34-47` restates the receipt template
from `we/references/verification.md:39-46`. That is user-facing output printed at deny time, not a
second definition of the rule — the operator being blocked cannot open a reference. Leave it.

## Defects

**1. `/code-review` has no defined pass criterion, so `review_passed` cannot be written by rule — the exact branch Scenario D takes.**
`we/references/integration-pipeline.md:102-104`:
> "Codex answers with JSON rather than a marker — `approve` → write `review_passed`;
> `needs-attention` → fix, re-run, then write it. Skip that mapping and the blocking gate in
> `pr-creator` never gets set."

The file names the consequence and defines the mapping for **one** of the two engines. In a
mixed-authorship wave the engine is always the other one, and `/code-review` emits neither JSON nor
a marker. Compare `we/agents/ac-reviewer.md:78-79`, which does define its verdict
(`<!-- VERDICT:PASS -->`). The Lead invents the criterion and `pr-creator` accepts whatever comes
of it.
*Smallest fix:* one line after `:104` — "Claude's native `/code-review` answers with a findings
list: zero findings at BLOCKING or WARNING → write `review_passed`; anything higher → fix, re-run,
then write it. Record the finding count in the checkpoint's `extra_data`." Severity: **highest** —
it is the gate this scenario walks into.

**2. The blocking checkpoint set contradicts itself across the two owning files.**
`we/references/integration-pipeline.md:154`:
> "**Blocking:** `review_passed`, `static_analysis_passed` and `test_passed` must all exist."

`we/agents/pr-creator.md:15`:
> "All 4 checkpoints must exist before PR creation:"

Three versus four; the pipeline drops `ac_verified` — the one checkpoint that also carries the
verification block (`integration-pipeline.md:88-89`). A Lead following the pipeline would dispatch
`pr-creator` believing it is clear, and `pr-creator` would STOP; or, worse, a Lead reading only the
pipeline hand-opens the PR without the AC gate.
*Smallest fix:* `integration-pipeline.md:154` becomes "the four checkpoints `pr-creator` requires
(`pr-creator.md` § Prerequisites) must all exist" — citation, not restatement. Severity: high.

**3. `pr-creator` cannot distinguish a real gate from a checkpoint someone typed, and is not asked to try.**
`we/agents/pr-creator.md:34-39`, its whole verification step:
> "### Step 2: Verify Checkpoints
> ```bash
> python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story status $TICKET
> ```
> **If ANY checkpoint missing → STOP. Tell the user which gates to run first.**"

`story_status()` returns rows of names (`we/scripts/orchestration.py:1319-1334`); `story_checkpoint()`
validates only that the name is in `STORY_PHASES` (`:1116-1124`). No verdict, no author, no evidence,
no ordering. In this wave all four rows are mine, two of them on judgement calls no artefact
records. The word "Verify" in the step title is not earned.
*Smallest fix:* make `story checkpoint` require `--evidence <path-or-marker>` for `ac_verified`,
`review_passed`, `static_analysis_passed`, `test_passed`, and have `pr-creator` Step 2 assert the
field is non-empty. Severity: high — it is the load-bearing gate before a public PR.
*And it is told the opposite of the truth about provenance:* its own table at
`we/agents/pr-creator.md:19` says `ac_verified` comes "From" `/we:ac-review`, and `:20` says
`review_passed` comes from the bug-hunt engine. Neither writes anything — see Defect 7.

**4. `integration-pipeline.md` restates the bug-hunt matrix in a form that answers Scenario D wrong.**
`we/references/integration-pipeline.md:99-101`:
> "**Exactly one bug-hunt engine runs, and the writer picks it: the engine that did *not* write the
> code.** The full matrix (Claude wrote + Codex configured → `/codex:adversarial-review`;
> otherwise Claude's native `/code-review`) is owned by `worker-dispatch.md` § Bug-hunt dispatch."

The parenthetical omits the mixed case. This wave *does* contain a Claude-written chunk and Codex
*is* configured, so the antecedent reads true and a Lead who trusts the summary dispatches
`/codex:adversarial-review` — Codex reviewing two chunks it wrote itself. `we/skills/setup/SKILL.md:175-177`
carries the same lossy copy. The correct rule survives only in `worker-dispatch.md:93-95` and
`orchestrate/SKILL.md:429-433`.
*Smallest fix:* delete the parenthetical at `:100`, leaving the citation. Severity: high.

**5. The parallel-gates instruction cannot be executed for the `/code-review` branch, and contradicts the file's own rule about `Skill()` in the Lead's context.**
`we/references/integration-pipeline.md:93`:
> "Launch all three in **one message** so they run concurrently:"

with `:97` "**one bug-hunt engine** → `review_passed`". `static-analyzer` and `test-runner` are
agents; `/code-review` is a skill, which runs in the Lead's own context, not concurrently — the
precise cost this same file forbids twenty lines later at `:169-171` ("**Never
`Skill(skill="ci-review")`** — that loads the skill into the main context and costs the Lead its
overview"). Nothing tells the Lead to wrap it in an Agent.
*Smallest fix:* at `:97`, "**one bug-hunt engine** — Codex via its Bash dispatch, or `/code-review`
inside `Agent(subagent_type="general-purpose", model="opus", …)` so it does not consume the Lead's
context". Severity: medium.

**6. No DoD row catches a chunk whose phase files never changed, and the one check that could is optional and produces no output row.**
`we/agents/ac-reviewer.md:50`:
> "- **Plan alignment?** Implementation matches the plan (if available)."

The parenthetical makes it skippable, and — decisively — the Output Format table at
`we/agents/ac-reviewer.md:98-108` has **no row for plan alignment**. The verdict at `:78-79` is
computed from ACs and DoD *rows* ("`<!-- VERDICT:BLOCKING -->` if any AC is unmet or any DoD item
Fails"), so a check with no row cannot fail the verdict. `we/quality/dod.md` has no phase-landing
item anywhere. The only two places the rule exists are `<repo>/.weside/dod.md` ("**Cross-repo
story: every phase landed**", scoped to multi-repo stories) and `we/skills/orchestrate/SKILL.md:449`
("a story is Done only when every `### Phase` block's `**Files:**` actually changed") — which sits
in Step 10, **after the human merged**. Nothing before the PR looks.
Same blindness covers the missing worker report: `orchestrate/SKILL.md:397` says "Read
`WORKER-REPORT.md`" per worker but has no branch for a chunk with no worker, and none of the four
files under test mentions worker reports at all.
*Smallest fix:* add to `we/quality/dod.md` § Code Quality — "**Every planned phase landed** — each
plan `### Phase` block's `**Files:**` actually changed in this diff; a phase with no worker report
is named in the PR body with who committed it and why" — and give it a row in
`ac-reviewer.md`'s Output Format table. Severity: medium-high (it is the scenario's fourth chunk).

**7. `pr-creator`'s prerequisites table asserts a provenance for two checkpoints that nothing implements.**
`we/agents/pr-creator.md:19-20`:
> "| `ac_verified` | `/we:ac-review` (AC-alignment + DoD) | Yes |
> | `review_passed` | Bug-hunt — Codex adversarial-review or Claude's native `/code-review` | Yes |"

The other two rows are honest — `we/agents/static-analyzer.md:56` and `we/agents/test-runner.md:61`
each run `story checkpoint "$TICKET" <phase>` under a stated condition. But no file anywhere in
`we/agents/` or `we/skills/` writes `ac_verified` or `review_passed`; `we/agents/ac-reviewer.md`
ends at a verdict marker and issues no checkpoint command, and `/code-review` is a native skill that
knows nothing about `orchestration.py`. `we/references/integration-pipeline.md:31-32` is correct
here — both rows say "Lead". So the two tables disagree on exactly the two rows where the writer is
the Lead's own judgement, and `pr-creator` is handed the version that names a gate. Combined with
Defect 3, `pr-creator` believes it is checking four gate outputs while two of them are self-reports.
*Smallest fix:* `pr-creator.md:19-20`'s "From" column reads "Lead, after the AC+DoD gate" and "Lead,
after the bug-hunt engine returned clean" — the truth, and it makes the weakness visible at the
point of use. Severity: medium-high.

**8. `review.cross` is documented as governing the bug-hunt and then documented as not governing it, and the matrix does not key on it.**
`we/references/worker-dispatch.md:78-81`:
> "To disable the per-chunk pass (integration still gates): `review.cross: false` in
> `.weside/config.json`. `review.cross` is the one flag that governs both the per-chunk
> AC-check and the bug-hunt dispatch below — turning it off skips the early, informational
> checks, not the final gate."

Clause two says it governs the bug-hunt; clause three says turning it off changes only the early
checks. The matrix at `:88-91` does not mention `review.cross`; `we/skills/setup/SKILL.md:175-176`
does ("Claude wrote + `tools.codex` + `review.cross` → `/codex:adversarial-review`"). What
`review.cross: false` does to engine selection is unanswerable from any of them. Related and
smaller: `worker-dispatch.md:90` keys row 1 on `tools.codex: true`, a key this repo's config does
not carry — it has `execution.default: "codex"`, which `orchestrate/SKILL.md:347` treats as
equivalent and `worker-dispatch.md` does not.
*Smallest fix:* delete "and the bug-hunt dispatch below" from `:80`, and change `:90`'s condition to
"`tools.codex: true` or `execution.default: codex`". Severity: medium.

**9. The per-chunk AC-check is required of workers that structurally cannot run it, and its absence leaves no artefact.**
`we/references/worker-dispatch.md:57`:
> "4. **AC-check own diff** (when `review.cross: true`) — see below"

and `:74`: "findings go into the report either way so the Lead sees them at integration". The
mechanism is `/we:develop` Step 5 (`develop/SKILL.md:137-146`), which a headless Codex worker never
runs; `worker-dispatch.md:52-55` itself says workers "can't load references". Two of four chunks
cannot comply, one had no worker to comply, and the artefact (`.reviews/…_<branch>_…`,
`ac-reviewer.md:73`) is branch-keyed so the integration pass cannot see even the compliant chunk's
review. Unfalsifiable prose.
*Smallest fix:* in `worker-dispatch.md` § AC-review rule, state that the per-chunk pass applies to
Claude-backend workers only, that a Codex or foreign chunk records `ac_check: not-available` in its
report, and that a chunk with no worker report is named by the Lead at integration. Severity: medium.

**10. `pr-creator` is told to copy a block it is never told where to find.**
`we/agents/pr-creator.md:71`:
> "the `## Verification` block from the build's verification step"

`integration-pipeline.md:82-83` says the receipt is written "into the story plan's `## Verification`
section (the receipt lives with the plan; `pr-creator` copies it into the PR body)" — but
`pr-creator.md` names no path, and its own Step 1 already knows `$TICKET`. In Scenario D the receipt
is complete and I copy it because I wrote it; a `pr-creator` on a fresh context has no instruction
to open `docs/plans/$TICKET-story.md`.
*Smallest fix:* `:71` → "the `## Verification` block, read verbatim from
`docs/plans/$TICKET-story.md` § Verification". Severity: medium (low for D, decisive elsewhere).

## Cuttable lines (no-ops for an Opus-class model)

1. `we/agents/pr-creator.md:99-107` — the entire `## Rules` block. Every one of its six bullets
   restates a numbered Step verbatim: *"- Verify all 4 checkpoints before creating the PR; stop if
   any is missing."* (= Step 2), *"- Rebase before pushing; save the `pr_created` checkpoint after
   success."* (= Steps 3, 9), *"- Transition the ticket → \"In Review\" in Step 8"* (= Step 8, and
   it says so). Only the last two bullets carry content not in a Step, and they belong in Steps 8
   and 9.
2. `we/agents/ac-reviewer.md:118` — *"- Review the **diff**, not entire files"*, already bolded at
   `:37`.
3. `we/agents/ac-reviewer.md:121` — *"- **ALWAYS save to file** before outputting verdict"*; Step 5
   is a whole section about saving to file.
4. `we/agents/ac-reviewer.md:122` — *"- Not your job: bug-hunting, security-vuln-hunting, code
   style"*; the Purpose block at `:10` opens with "This agent never hunts bugs".
5. `we/agents/ac-reviewer.md:52-54` — *"(see `${CLAUDE_PLUGIN_ROOT}/quality/dod.md` if available,
   otherwise apply the four criteria: architecture patterns followed, security patterns applied,
   state wiring complete, tests verify behaviour)"*. The fallback is a fifth copy of four DoD rows;
   `quality/dod.md` ships with the plugin and is not "if available".
6. `we/agents/pr-creator.md:30-31` — *"the key is regex-extractable because the pipeline puts it
   first (`{type}/{TICKET}-description`)"*. Explaining to a model why a prefix is extractable.
7. `we/quality/dod.md:144-145` — *"A story is DONE when every applicable box above is ticked —
   **awaiting the user's merge**…"*, which is `:3` plus `:118`.
8. `we/quality/dod.md:30`, `:63`, `:106` — the three *"Not applicable → skip"* / *"Nothing above
   applies → skip"* bullets. A checklist item that says "skip the items that do not apply" adds a
   row to `ac-reviewer`'s output table and no decision.
9. `we/agents/ac-reviewer.md:119` — *"- Every AC gets its own row — no bundling several ACs into one
   verdict line"*; the Output Format at `:91-93` is a per-AC table and `:46-47` already says it.
10. `we/quality/dod.md:132-140` § Review Output Format — *"`we:ac-reviewer` … should include in its
    output: 1. **AC Alignment Table** … 2. **DoD Quick Check**"*. `ac-reviewer.md:83-112` is the
    authoritative Output Format; this is a vaguer second copy in the file `ac-reviewer` reads for
    its rows.

## What I needed and did not find

- **A pass criterion for `/code-review`.** Defect 1. Every other verdict in the system has a marker
  or a JSON key; this one has nothing, and it is the one a mixed wave always hits.
- **Any way to tell `we:ac-reviewer` who wrote which chunk.** Its Step 1 takes a branch and a
  ticket; nothing carries authorship, worker reports, or the per-chunk review state into it. The
  brief asks whether it "knows or cares" — it cannot know, so the question of caring never arises.
- **An artefact that distinguishes a skipped per-chunk AC-check from an impossible one.** `.reviews/`
  is branch-keyed and therefore invisible at integration.
- **A pre-PR check that every planned phase landed.** The rule exists twice — once scoped to
  cross-repo stories in `<repo>/.weside/dod.md`, once post-merge in `orchestrate/SKILL.md:449` — and
  never where the fourth chunk of this wave would meet it.
- **A single owner for the bug-hunt matrix.** Four copies, two of them wrong for this scenario.
- **Something, anywhere, that reads a checkpoint's provenance.** `extra_data` exists in the schema
  and no consumer reads it — while `pr-creator.md:19-20` prints a provenance it cannot verify.

## Grade

**2** — the pipeline routes Scenario D correctly and the verification hook is genuinely sound, but
the gate the scenario actually walks into has no defined pass criterion (`/code-review` →
`review_passed`), the file that owns the step restates the engine matrix in a form that answers this
wave wrong, and `pr-creator`'s "Verify Checkpoints" verifies only that four strings were typed.
