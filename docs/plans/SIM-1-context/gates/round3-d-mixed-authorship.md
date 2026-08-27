---
type: simulation-report
chunk: gates
scenario: D — mixed-authorship wave
round: 3
grade: 4
---
# Round 3 · Scenario D

Same wave: four chunks on `feat/TICKET-101-integration` — two by headless Codex workers, one by a
Claude `sonnet` worker, one committed by the Lead after a worker died without pushing. Receipt
complete. I re-run cold from the parallel-quality-gates step, then judge round 2's findings and
the revision itself.

Scope: the four revised files are `we/agents/ac-reviewer.md`, `we/agents/pr-creator.md`,
`we/quality/dod.md`, `we/hooks/verification_gate.py`. `we/references/*.md` and
`we/skills/*/SKILL.md` are not in the chunk's file list — a defect there is a FORK.

## Verdict on round 2

Round 2's ten round-1 carry-overs, then its own seven Still-open/new items.

| # | Round-2 finding | Verdict | Evidence (current line) |
|---|---|---|---|
| D1 | `review_passed` has no defined pass criterion | **PARTIALLY — IN-SCOPE** | A criterion now exists: `dod.md:76` "- [ ] Bug-hunt passed (`review_passed` checkpoint) — clean means no BLOCKING or WARNING finding left unfixed by the one engine that ran, whichever it was". See Still-open 2: it is written in a vocabulary this wave's engine does not speak |
| D2 | Blocking checkpoint set: three vs four | **STILL OPEN — FORK** | `pr-creator.md:13-18` four rows under "## Prerequisites (BLOCKING)"; `integration-pipeline.md:154` "**Blocking:** `review_passed`, `static_analysis_passed` and `test_passed` must all exist." |
| D3 | `pr-creator` cannot tell a real gate from a typed checkpoint | **STILL OPEN — IN-SCOPE (half)** | `pr-creator.md:31` `story status $TICKET`, `:34` "**If any of the four above is missing → STOP.**" — no verdict, author or evidence field. The `--evidence` half is `orchestration.py`, a FORK |
| D4 | `integration-pipeline.md` restates the engine matrix wrongly for D | **STILL OPEN — FORK** | `integration-pipeline.md:100-101` "(Claude wrote + Codex configured → `/codex:adversarial-review`; otherwise Claude's native `/code-review`)" — in this wave Claude *did* write one chunk and Codex *is* configured |
| D5 | Parallel-gates instruction not executable for the `/code-review` branch | **STILL OPEN — FORK** | `integration-pipeline.md:93` "Launch all three in **one message** so they run concurrently:" against `:97` "**one bug-hunt engine** → `review_passed`" — a skill runs in the Lead's own context, not as a concurrent agent |
| D6 | No DoD row catches a chunk whose phase files never changed | **FIXED** | `dod.md:18`; `ac-reviewer.md:56-57`; output row `ac-reviewer.md:97` |
| D7 | `pr-creator`'s table asserts a provenance nothing implements | **FIXED** (round 2) | `pr-creator.md:15-16`, agreeing with `integration-pipeline.md:31-32` |
| D8 | `review.cross` documented as governing the bug-hunt and as not | **STILL OPEN — FORK** | `worker-dispatch.md:79-81` "`review.cross` is the one flag that governs both the per-chunk AC-check and the bug-hunt dispatch below — turning it off skips the early, informational checks, not the final gate." Two halves of one sentence disagree |
| D9 | Per-chunk review artefact invisible at integration | **STILL OPEN — IN-SCOPE (half)** | `ac-reviewer.md:45` "Look for an earlier review for this branch under `.reviews/`" against `:67` "Write to `.reviews/<YYYYMMDD-HHMM>_<branch>_V<n>.md`" |
| D10 | `pr-creator` told to copy a block it is never told where to find | **FIXED** (round 2) | `pr-creator.md:64-66`, `:68-72` |

| # | Round-2 Still-open / new | Verdict | Evidence |
|---|---|---|---|
| R2-1 | "Every planned phase landed" defined in two files, already diverging | **PARTIALLY — IN-SCOPE** | Duplication FIXED: `ac-reviewer.md:56-57` now cites instead of defining — "every applicable row of `${CLAUDE_PLUGIN_ROOT}/quality/dod.md` — it owns the definitions, including *Every planned phase landed*, which is a Fail whoever committed the phase." The clause that made it Scenario D's row is still unimplemented, and now silently deferrable — Still-open 1 |
| R2-2 | D1 | **PARTIALLY** — above and Still-open 2 | |
| R2-3 | `dod.md`'s replacement citation mis-describes `ac-reviewer.md` | **PARTIALLY** | `dod.md:134-135` now "fills a row per applicable item **or section** above", matched by `ac-reviewer.md:58-59` "A section with no fixed row in the format below gets a row of its own, `N/A` with its reason when nothing in it applies." The residue is Still-open 4 |
| R2-4 | Register regeneration at two pipeline stages | **FIXED as written, reopened as a stage** | The regeneration sentence is gone from `pr-creator.md`; `integration-pipeline.md:149-150` is the sole owner. What replaced it re-creates the overlap in a wider form — Still-open 3 |
| R2-5 | Step 2's scope word cut with the `## Rules` block | **FIXED** | `pr-creator.md:34` "**If any of the four above is missing → STOP. Tell the user which gates to run first.**" |
| R2-6 | D3 | **STILL OPEN** — above | |
| R2-7 | D9 | **STILL OPEN** — above | |

## Duplications, re-checked

| Rule | Owner now | Citations elsewhere | Verdict |
|---|---|---|---|
| Bug-hunt engine matrix | `worker-dispatch.md:83-95` | `ac-reviewer.md:10-11` cites it ✓ · `dod.md:135-136` "The bug-hunt engine reports separately — `worker-dispatch.md` § Bug-hunt dispatch." ✓ · `integration-pipeline.md:100-101` still restates lossily | **PARTIALLY** — both in-scope copies are citations; the wrong copy is a FORK |
| What "clean" means for `review_passed` | **now exists**: `dod.md:76` | `integration-pipeline.md:102-104` states an engine-specific mapping ("`approve` → write `review_passed`") without citing it | **PARTIALLY** — owner established this round; the FORK copy is a second, narrower criterion |
| Blocking checkpoint set | contested | `pr-creator.md:13-18` (4) · `dod.md:75-78` (4) · `integration-pipeline.md:154` (3) | **PARTIALLY** — writer column agrees, count still does not |
| A DoD Fail blocks like an unmet AC | `dod.md:122-123` | `ac-reviewer.md:73` is the verdict mechanism, legitimate · `integration-pipeline.md:66` still a verbatim restatement | **FIXED (owner)**, one FORK copy |
| Every planned phase landed | `dod.md:18` | `ac-reviewer.md:56-57` cites the owner but adds a gloss the owner does not carry ("a Fail whoever committed the phase") · row note `ac-reviewer.md:97` | **PARTIALLY** — one definition, one earned gloss, one table note |
| `.weside/dod.md` is additive, never a replacement | `dod.md:5` | `ac-reviewer.md:60-63` restates ("**additive and mandatory when it is there**, never a replacement") · `integration-pipeline.md:65-66` restates | **STILL OPEN** — three statements, no citation; wording now agrees in intent, so this is the weakest row here |
| Each AC verified individually with evidence | `dod.md:14` | `ac-reviewer.md:50-54` is the filling mechanism, legitimate · `integration-pipeline.md:59-61` is a plain restatement | **PARTIALLY** — one FORK copy |
| Feature reachable / end-to-end | `dod.md:15-16` | `ac-reviewer.md:55` · `verification.md:27` · `<repo>/.weside/dod.md` item 4 | **STILL OPEN** — unchanged |
| Receipt fields (oracle / seed / asserted / not proven) | `verification.md:39-46` | `dod.md:33-34` cites the contract ✓ · `ac-reviewer.md:18-21` states the blocking rule, not the format ✓ · `verification_gate.py:96-105` enumerates a **subset** | **STILL OPEN — NEW severity**, Still-open 5 |
| Deliberate bypasses + register regeneration | `dod.md:26-29` | `ac-reviewer.md:102` row ✓ · `integration-pipeline.md:149-150` (docs step) | **FIXED** — `pr-creator`'s third copy is gone |
| Repo-local pre-PR gate runs | contested | `integration-pipeline.md:109-115` and `pr-creator.md:42-45` | **NEW** — Still-open 3 |
| Never move to Done / the human merges | `dod.md:116` | `pr-creator.md:81-82` (transition) and `:104` (merge) — two distinct actions ✓ · `integration-pipeline.md:198` | **PARTIALLY** |
| Horizontal scalability / `SCALABILITY-EXEMPT` | `dod.md:59-62` | `ac-reviewer.md:103` row only | **FIXED** |

Intra-file self-duplication: none found in any of the four revised files.

## Trace

Cold, from the parallel-quality-gates step.

1. **Bug-hunt engine.** `worker-dispatch.md:93-95` (unrevised): "Mixed authorship in one wave (a Codex chunk beside Claude chunks, or a tree the Lead committed for a dead worker) counts as \"anything else\": Claude's native `/code-review` over the whole integrated diff." Engine = **`/code-review`**. Had I read `integration-pipeline.md:100-101` instead, its parenthesis ("Claude wrote + Codex configured → `/codex:adversarial-review`") would have sent me to Codex — one Claude chunk was written and `tools.codex` is on. D4 is still the trap of this scenario.
2. **Launching the three gates.** `integration-pipeline.md:93` wants one message; two of the three are `Agent(...)` calls and the third is a skill in my own context. I dispatch the two agents and run `/code-review` myself. D5.
3. **`review_passed`.** `/code-review` returns a findings list — correctness bugs and reuse/simplification cleanups at the requested effort. `dod.md:76` now tells me what clean means: "no BLOCKING or WARNING finding left unfixed by the one engine that ran, whichever it was." I have findings with no severity labels on them. `dod.md:125-128` gives the ladder (BLOCKING/WARNING = MUST fix; INFO/NITPICK = fix or document skip reason) but nothing says who assigns a `/code-review` finding to a rung. **Answer to the brief's question: a criterion now exists and I can quote it, but for this wave's engine I still supply the severity assignment myself, unrecorded.** I fix the two findings I judge real, call the rest nitpicks, and write `story checkpoint TICKET-101 review_passed`.
4. **AC + DoD gate — does the fourth chunk meet a check before the PR?** Yes. `we:ac-reviewer` reads the plan (`ac-reviewer.md:31`), so it holds the `### Phase` blocks, and Step 4 sends me to the owner: `ac-reviewer.md:56-57` "every applicable row of `${CLAUDE_PLUGIN_ROOT}/quality/dod.md` — it owns the definitions, including *Every planned phase landed*, which is a Fail whoever committed the phase." The row exists in the output format at `ac-reviewer.md:97` "| Every planned phase landed | Pass/Fail | Each plan phase's `**Files:**` changed in this diff |", and `:73` makes it blocking. The Lead-committed chunk's files did change → **Pass**, correctly.
   The half of `dod.md:18` that exists *because* of a dead worker — "a phase committed by someone other than its worker is named in the PR body with who did it and why" — cannot be evidenced at this gate, because no PR body exists. `ac-reviewer.md:52-54` now tells me exactly what to do with that: "unless the evidence cannot exist yet at this gate (the PR, CI, the ticket move), which is `N/A` naming the stage that owes it." I write `N/A — owed by pr-creator`. Nothing at `pr-creator` collects it (Still-open 1).
5. **PR step.** `Agent(subagent_type="we:pr-creator", prompt="Create PR for TICKET-101")`. Step 2 runs `story status TICKET-101`; all four Prerequisites rows exist, two of them written by me, one on the judgement in step 3. Step 3b (`:42-45`) tells me to run the repo's `scripts/check-*.sh` — which I already ran at the quality-gates step per `integration-pipeline.md:109-115`. They pass; had one gone red, `:44-45` excuses only a *missing* script and says nothing about a failing one (Still-open 3).
6. **Step 7 → the hook.** Body written to a file (`pr-creator.md:62` "Write the body to a file and pass it as `--body-file`"), `## Verification` copied verbatim from `docs/plans/TICKET-101-story.md`. `verification_gate.py`: `_pr_verb` finds `create` in command position, `_required` reads `verification.required: true`, `_body_of` reads the file, `_receipt_problem` finds the heading, `_oracles` returns `{"cli"}` (one named oracle, not the four-way menu), `_filled(body,"seed")` and `_filled(body,"asserted")` both true → `_refusal` returns None. **Pass.**
7. **Step 9.** `story checkpoint TICKET-101 pr_created`. PR open, nothing named who committed the fourth chunk.

**Which gate stops what, with which message**

| Gate | Stops | Message | Stops anything in D? |
|---|---|---|---|
| `verification_gate.py` | a `create` with no body flag; a body with no receipt or a menu oracle; a bare `not-applicable`; an unfilled seed/asserted | `:266-267` "This PR is opened with no body at all, so it claims work is done and says nothing about how that was observed." · `:226-227` "This PR claims work is done without saying how that was observed. Unit tests do not count…" · `:233-235` "`not-applicable` is a legitimate answer and it carries its reason — say what about this change has no runtime behaviour to observe." · `:239-241` "This PR carries a `## Verification` heading over an unfilled receipt…" | No — the receipt is real |
| `we:ac-reviewer` Step 6 | an unmet AC or any Failing DoD row | `:73` "`<!-- VERDICT:BLOCKING -->` if any AC is unmet or any DoD row Fails" | Would stop a *vanished* phase. Does not stop an *unattributed* one — `:52-54` routes it to `N/A` |
| `pr-creator` Step 2 | one of four checkpoint names absent | `:34` "**If any of the four above is missing → STOP. Tell the user which gates to run first.**" | No — four names exist; two are my own judgement |
| `dod.md` § Quality Gates | — | `:76` now states the criterion | No, and for this engine it only half-states it |

**Answers:** engine = Claude's native `/code-review` (`worker-dispatch.md:93-95`); checkpoint = `review_passed`, now written against a stated criterion whose severity vocabulary this engine does not emit; `pr-creator` accepts it — Step 2 still verifies only that the string exists.

## Still open / new

1. **NEW (in-scope, two files) — the clause that exists for Scenario D is orphaned, and the new escape makes the orphaning silent.** `dod.md:18`:
   > "- [ ] **Every planned phase landed** — each plan `### Phase` block's `**Files:**` actually changed in this diff; a phase committed by someone other than its worker is named in the PR body with who did it and why."

   Nothing collects the second clause. `pr-creator.md:64-66` lists the body's contents — "**Summary**, **Changes** (from the commits), **Test Plan**, the ticket key on its own line so the ticket auto-links, and the `## Verification` block **copied verbatim from `docs/plans/${TICKET}-story.md` § Verification**" — with no attribution line. Round 2 filed this as "defined in two files and already diverging"; the revision fixed the duplication (`ac-reviewer.md:56-57` cites the owner) and left the clause without an implementer. What is worse than round 2: `ac-reviewer.md:52-54` now says
   > "unless the evidence cannot exist yet at this gate (the PR, CI, the ticket move), which is `N/A` naming the stage that owes it"

   so the AC gate no longer even *fails* on it — it defers it to a stage with no instruction to collect it. Concrete failure: this wave's fourth chunk was committed by the Lead for a dead worker, passes the row, and the PR names nobody.
   *Smallest fix:* add to `pr-creator.md:64-66` "and, for any plan phase committed by someone other than its worker, one line naming who committed it and why" — or cut the clause from `dod.md:18` so the row means only what it can check. **IN-SCOPE.**

2. **PARTIALLY (D1) — the pass criterion is written in the other engine's vocabulary.** `dod.md:76`:
   > "- [ ] Bug-hunt passed (`review_passed` checkpoint) — clean means no BLOCKING or WARNING finding left unfixed by the one engine that ran, whichever it was"

   Codex answers `approve` / `needs-attention` (`integration-pipeline.md:102-104`). Claude's native `/code-review` — the engine `worker-dispatch.md:93-95` mandates for exactly this wave — returns a findings list at an effort level, with no BLOCKING/WARNING labels on it. `dod.md:125-128` supplies the ladder but not who maps a finding onto it. Real improvement over round 2's nothing; not yet a rule I can apply without inventing the severity, which is the unrecorded judgement D1 named.
   *Smallest fix:* `dod.md:76` → "…no finding left unfixed that the Lead does not record as INFO/NITPICK with its reason (`§ Issue Severity`); Codex's `needs-attention` is a WARNING." **IN-SCOPE.**

3. **NEW (in-scope) — Step 3b runs a stage the pipeline already owns, and has no red path.** `pr-creator.md:42-45`:
   > "### Step 3b: Repo-local pre-PR gates
   > Run whatever pre-PR check scripts the repo ships (`scripts/check-*.sh` and friends) before pushing; a missing script is an absent gate, not a failure."

   against `integration-pipeline.md:109-112` "**Install-gated gates run here too, not at CI.** … The integration worktree is the one place in the run that can afford the install — so install once and run them over the *merged* diff." That step runs before docs and before the PR. Two consequences. (a) The scripts run twice — in a repo whose `check-*` set includes an OpenAPI freshness check and bypass gates, that is minutes for no new signal; round 2's New 4 was the same class, relocated rather than removed. (b) The sentence excuses only a *missing* script; a **failing** one has no instruction — stop, fix, or push anyway is undefined at the one step whose next action is `git push --force-with-lease` (`:49`).
   *Smallest fix:* `pr-creator.md:44-45` → "Confirm the repo's pre-PR gates were run at the quality-gates step (`references/integration-pipeline.md` § Quality gates); a red one means that step was skipped — stop and say so." **IN-SCOPE.**

4. **PARTIALLY (R2-3) — the section rule still leaves the semantic-check items unrowed.** `dod.md:134-135` "fills a row per applicable item or section above" is now matched by `ac-reviewer.md:58-59` "A section with no fixed row in the format below gets a row of its own, `N/A` with its reason when nothing in it applies." § Post-Implementation Semantic Checks *has* fixed rows (State wiring, Horizontal scalability), so it is not "a section with no fixed row", and its remaining items get neither a fixed row nor a section row. Concrete failure in this wave: the diff carries `alembic/versions/9f2_widgets.py`, and `dod.md:49-50` "**Migrations run and reverse** — applied locally, and idempotent … so a re-run is not a failure" is checked by no row in `ac-reviewer.md:93-105`.
   *Smallest fix:* `ac-reviewer.md:58-59` → "…gets a row of its own; so does any item in a section whose fixed rows do not cover it." **IN-SCOPE.**

5. **NEW (in-scope) — the hook's denial message states a receipt one field shorter than the contract it cites.** `verification_gate.py:96-101`:
   > "It needs one `**Oracle:**` — cli | ui | substitute | not-applicable — and, unless that oracle is not-applicable, a filled `**Seed:**` and `**Asserted:**`."

   against `verification.md:39-46`, which owns the format and requires `**Not proven:** <what this oracle cannot show, and who owes it>`, and `dod.md:34` "oracle, seed, what was asserted, what stays unproven. No block, no claim of verified." Round 2 exempted the hook's deny-time text as output rather than a rule copy; that exemption does not cover a copy stating a *lower* bar than the owner, because this is the text the author reads at the moment they are fixing the body — and the whole point of "**State what failed, if something did.** A receipt that only ever says \"works\" is decoration" (`verification.md:52-53`) lives in the field the message drops.
   *Smallest fix:* `_WHERE` stops enumerating — "…copy it verbatim; its fields are owned by the `we` plugin's references/verification.md § The receipt. This gate additionally refuses a heading over an unfilled seed or assertion." **IN-SCOPE.**

6. **STILL OPEN (D3) — Step 2 verifies that four strings were typed.** `pr-creator.md:31` `story status $TICKET`, `:34` quoted above. In this wave `ac_verified` and `review_passed` are both mine, one on the judgement in Trace step 3. **IN-SCOPE** for `pr-creator.md`; the `--evidence` half is `orchestration.py`, a FORK.

7. **STILL OPEN (D9, in-scope half) — the per-chunk review artefact stays invisible at integration.** `ac-reviewer.md:45` "Look for an earlier review for this branch under `.reviews/`" against `:67` "Write to `.reviews/<YYYYMMDD-HHMM>_<branch>_V<n>.md`". The integration branch is `feat/TICKET-101-integration`; every chunk review is filed under a chunk-branch name, so an absent entry stays indistinguishable between `review.cross: false`, a Codex worker that structurally cannot run it, and the worker that died.
   *Smallest fix:* `ac-reviewer.md:45` → "…for this branch **and for any branch merged into it** under `.reviews/`". **IN-SCOPE.**

8. **STILL OPEN — FORKS, re-verified unchanged:** D2 (`integration-pipeline.md:154`), D4 (`integration-pipeline.md:100-101`), D5 (`integration-pipeline.md:93` vs `:97`), D8 (`worker-dispatch.md:79-81`), D9's dispatch half (`worker-dispatch.md:57`).

## Judging the revision by its own standard

`pr-creator.md` 105 → 104 lines, `dod.md` 137 → 136, `ac-reviewer.md` 104 → **109**. The growth is not padding: `:16-21` gives the agent one check it owns outright ("**One check is yours alone:** the DoD's *Verification* items … a `## Verification` block that is missing … is BLOCKING. `not-applicable` with a stated reason is a Pass; silence is not."); `:52-54` and `:58-59` turn two round-2 gaps into rules; `:56-57` converts a rival definition into a citation. Every one of those lines steers.

The best trades this round: `dod.md:76` gained a criterion where round 2 had a bare gate name, and `pr-creator`'s Step 3b *lost* the register-regeneration duplication. The hook kept hardening — `_receipt_problem`'s `not-applicable` branch (`:228-236`) is new and enforces `verification.md:56-57` ("must carry its reason"), and `_body_of`'s `cd` handling (`:186-187`) closes the `cd x && gh pr create` path. Three shapes that reached `gh` in round 1 now deny.

**Cuts that removed something I needed:** none. Round 2's one complaint — the word "four" in Step 2's stop condition — is restored at `pr-creator.md:34`. `dod.md:76` dropped the parenthetical naming the two engines, and that cut is right: `dod.md:135-136` cites `worker-dispatch.md` for the engine, so the owner stayed single. The three "skip" no-ops round 2 wanted gone (`dod.md:29`, `:46`, `ac-reviewer.md:63`) survived; each one now changes behaviour rather than restating a default, so I withdraw that objection.

## Grade

**4** — I can run this wave cold and most gates answer with a rule. Six of round 2's seven Still-open/new items closed, including both self-inflicted contradictions; the phase-landing rule now has one owner and a row that can fail the verdict *before* the PR; `review_passed` acquired the criterion it never had; the hook is stronger again. Held below 5 by three things a fifth round would still hit, all in-scope: the attribution clause that exists for exactly this scenario has no implementer and is now silently `N/A`-able (Still-open 1); the new criterion speaks Codex's vocabulary while `worker-dispatch.md:93-95` mandates `/code-review` for this wave (Still-open 2); and Step 3b duplicates a pipeline stage with no instruction for a red result (Still-open 3). Held well above 3 because none of those is a gate that answers *nothing* — each is a gate that answers, and answers one clause short.
