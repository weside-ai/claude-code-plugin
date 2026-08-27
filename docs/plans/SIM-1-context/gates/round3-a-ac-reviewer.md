---
type: simulation-report
chunk: gates
scenario: A — ACs met, one repo DoD row violated
round: 3
grade: 4
---
# Round 3 · Scenario A

I am `we:ac-reviewer`, dispatched once at integration against the full merged diff of
`TICKET-101` on `feat/TICKET-101-integration`. Table-top only: every tool call is traced,
nothing is executed, and the only file I write is this report.

## Verdict on round 2

Round-2 findings, numbered as its *Still open / new* section numbers them.

| # | Round-2 finding | Verdict | Evidence (quoted current line) |
|---|---|---|---|
| 1 | The Fail-not-Pass rule makes every review BLOCKING forever | **PARTIALLY** | `ac-reviewer.md:52-54` now reads *"one you cannot cite evidence for is a Fail, not a Pass — unless the evidence cannot exist yet at this gate (the PR, CI, the ticket move), which is `N/A` naming the stage that owes it."* That is the round-2 smallest fix, and it disarms `dod.md:108-116` (`PR created`, `CI passed`, the two ticket moves) and `:40` *"Coverage meets project thresholds (verified by CI on push — not a local gate)"*. The parenthetical does **not** cover the local gates that run *after* this one — see *Still open / new* #1. |
| 2 | Plugin items get nine fixed rows, repo items get one row each | **FIXED** | `ac-reviewer.md:58-59` — *"A section with no fixed row in the format below gets a row of its own, `N/A` with its reason when nothing in it applies."* `dod.md:134` agrees from the other side: *"`we:ac-reviewer` fills a row per applicable item or section above"*. § Evidence, § Quality Gates, § Documentation, § CI/CD and § Ticketing now have a home. Residual: the Output Format template shows no slot for those rows — *Still open / new* #3. |
| 3 | `:58` forces the same check to be written four times | **FIXED** | `ac-reviewer.md:62-63` — *"One row per item, except an item a fixed row already carries: name that row instead of repeating it."* In this run it collapses four redundant rows (three verification-class repo items into the fixed *Verification receipt* row, *Cross-repo story: every phase landed* into *Every planned phase landed*). My repo block drops from 13 rows to 9 plus three named-not-repeated. |
| 4 | The receipt's location is never named (round-1 D2) | **FIXED** | `ac-reviewer.md:18-20` — *"a `## Verification` block that is missing — from the story plan at integration, from the PR body once a PR exists — or that only names unit tests, is BLOCKING."* The false-BLOCKING path is closed at the point of use, and it interlocks with `:52-54`: `dod.md:34` *"**The PR carries a `## Verification` block**"* and `<repo>/.weside/dod.md:66` now land as `N/A` naming `pr-creator`, not as a Fail. `dod.md:5` adds a second agreeing authority — *"the `we:ac-reviewer` agent reads it additively — both the checklist below and the repo file apply"*. This is the round's biggest win. |
| 5 | A severity table with two identical rows and no reader left | **FIXED** | `dod.md:127` — `\| **BLOCKING / WARNING** \| MUST fix \|` — one row, exactly the round-2 smallest fix, and `:122-123` *"there is no second, softer tier for 'only' the DoD"* no longer contradicts the table under it. |
| 6 | A DoD item about the plan, checked against a diff | **FIXED** | `dod.md:19` — *"**Parallelisation considered** (checked at DoR, not at the AC gate)"*. The annotation is enough: I skip it without a row and without a deviation. |
| 7 | No channel for declaring a deviation from the mandated Output Format | **FIXED by removing its cause** | Round 2 said *"If #1 is fixed, this one disappears with it."* `:52-54` removes the forced `N/A`-where-`Fail`-was-demanded deviation, so this run has **zero** undeclared deviations (round 2 had one, round 1 two). Its residual is the template slot in *Still open / new* #3. |
| 8 | Three cosmetic duplications | **STILL OPEN** | All three lines are unchanged: `ac-reviewer.md:13-14` *"**Guiding question:** Does this diff actually satisfy what was asked — and is it done, not just built?"* under `:9-10`; `dod.md:13` *"Code implemented and functional"* one line above `:14`; `dod.md:110` *"All BLOCKING/WARNING issues fixed"*, which now restates `:76` (*"clean means no BLOCKING or WARNING finding left unfixed"*) rather than the collapsed table. Zero behavioural delta; three lines. |

## Trace

**0 — What I load.** My own file. It names, by path: `references/ticketing.md` (`:30`),
`${CLAUDE_PLUGIN_ROOT}/quality/dod.md` (`:56`), `<repo-root>/.weside/dod.md` with its detection
command (`:60`). Still not named: `.weside/config.json`, `references/verification.md`,
`references/integration-pipeline.md`. Unchanged from round 2 and no longer costly — the two
things I used to need those files for (the receipt's location, the downstream-evidence
exception) are now in my own file.

**1 — Step 1, branch + key.** `Bash("git rev-parse --abbrev-ref HEAD")` →
`feat/TICKET-101-integration`. Key `TICKET-101`.

**2 — Step 1, ticketing.** `:30` routes me: `Read("we/references/ticketing.md")` → weside MCP
first, Atlassian MCP second. `ToolSearch("select:mcp__atlassian__jira_get_issue")`, then
`jira_get_issue(issue_key="TICKET-101", comment_limit=20)`. Ticket ACs match the plan's three.

**3 — Step 1, the plan.** `Read("docs/plans/TICKET-101-story.md")` → three ACs, a complete
`## Verification` (oracle `cli`, seed, asserted, not-proven, plus a walkthrough note for AC 2),
and the `### Phase` blocks I need for `:56-58`.

**4 — Step 2, the diff.** Derive the base: `Bash("gh pr view --json baseRefName")` → no PR at
this gate; `Bash("git symbolic-ref refs/remotes/origin/HEAD")` → `origin/main`.
`Bash("git status --porcelain")` → clean. `Bash("git diff origin/main...HEAD")` → eight files.
`:37-39` keeps a dirty tree from scoping the review down to one stray file.

**5 — Step 3, previous reviews.** `Glob(".reviews/*")` → nothing. V1.

**6 — Step 4, ACs.** Three rows, each cited. AC 2's reachability is the UI→endpoint call path:
`WidgetsScreen.tsx` calls `POST /api/v2/widgets` and the screen is registered in the navigator,
both inside the diff.

**7 — Step 4, the receipt.** `:18-20` tells me where to look **before** I open any DoD:
the story plan at integration. I read it from `docs/plans/TICKET-101-story.md § Verification`
and Pass the row. Round 2 reached the same place by inference from silence; round 3 is
instructed. When I then hit `dod.md:34` and `<repo>/.weside/dod.md:66` — both worded *"The PR
carries a `## Verification` block"* — `:52-54` gives me `N/A`, *"naming the stage that owes it"*
(`pr-creator`, `pr-creator.md:65-66` *"copied verbatim from `docs/plans/${TICKET}-story.md`
§ Verification"*). Two rows that were a false-Fail hazard in round 2 now resolve cleanly.

**8 — Step 4, phases landed.** Here I took a wrong reading and backed out of it.
`ac-reviewer.md:56-58`: *"every applicable row of `${CLAUDE_PLUGIN_ROOT}/quality/dod.md` — it
owns the definitions, including *Every planned phase landed*, which is a Fail whoever committed
the phase."* The relative clause can attach to the **row** ("this row is a Fail, period"). I
resolved it against `dod.md:18` — *"a phase committed by someone other than its worker is named
in the PR body with who did it and why"* — which is a naming requirement, not an automatic Fail,
and read the sentence as "authorship does not excuse a phase that did not land". In Scenario A
all three phases landed and each was committed by its own chunk worker, so the row is **Pass**
under either reading and the wrong read cost me nothing here. It would decide a mixed-authorship
wave. *Still open / new* #2.

**9 — Step 4, plugin DoD by section.** `Read("${CLAUDE_PLUGIN_ROOT}/quality/dod.md")`. Nine
fixed rows cover Verification, phases, architecture, security, wiring, tests, bypasses,
scalability, TODO. Per `:58-59` I add a row for each section with no fixed row: § Evidence,
§ Quality Gates, § Documentation, § CI/CD, § Ticketing. § CI/CD and § Ticketing are `N/A` under
`:52-54`'s exception. § Documentation is a Pass (docstrings written on the new service and CRUD;
no generated artefact in scope). § Evidence is a Pass from the commit messages. **§ Quality
Gates is where the file stops helping me** — see the next step.

**10 — The one decision the file does not settle.** § Quality Gates holds `dod.md:75`
*"AC-review passed (`ac_verified` checkpoint …)"* — written about this very review — and
`:76-78` `review_passed` / `static_analysis_passed` / `test_passed`, which
`integration-pipeline.md:91` § *Quality gates (parallel)* places **after** this gate, and
`:88` confirms (*"Checkpoint `ac_verified` only when every AC passes, every DoD row passes"* —
i.e. I run first). I cannot cite evidence for any of them. `:58-59` offers `N/A` only *"when
nothing in it applies"*, and these items do apply to this story — they simply have not happened
yet. `:52-54`'s exception names *"the PR, CI, the ticket move"* and not these. I wrote `N/A` on
the grounds that a gate that runs after me is the same class the exception describes, but the
file lets a cold reader land on `Fail` just as defensibly, and `:73` then returns BLOCKING.
*Still open / new* #1.

**11 — Step 4, repo DoD.** `Bash("git rev-parse --show-toplevel")`, then
`Read("<repo>/.weside/dod.md")`. `:60-63` leaves nothing to decide — additive, mandatory, one
row per item except where a fixed row already carries it. Nine own rows, three named into the
*Verification receipt* row, one (*Cross-repo story: every phase landed*) named into *Every
planned phase landed*.

**12 — The finding.** `<repo>/.weside/dod.md:17-21`: *"**New LLM call site → billing wiring
shown** — a diff that adds an LLM call site outside `CompanionBeing` demonstrates its money path
(reservation+settle wrap OR the `meter()` `deduct()` branch) and ships/extends a net-effect test
(Σ mutations == Σ ledger)."* Against the diff: `app/services/widget_summary.py` calls
`LLMFactory.get_chat_model()` then `ainvoke` with no reservation, no settle, no `meter()`, and
`tests/services/test_widget_summary.py` mocks the chat model and asserts a string. **Fail.**
`<repo>/.weside/dod.md:26-28` (*"**Money-path concurrency + reversal**"*) Fails on the same site.
Nothing in `quality/dod.md` names this class.

**13 — Step 5, save.** `.reviews/20260827-1430_feat-TICKET-101-integration_V1.md` per `:67-68`.
*(Traced only; I create no file.)*

**14 — Step 6, verdict.** `:73` — a DoD row Fails → `<!-- VERDICT:BLOCKING -->`.

### The verdict I would have written, verbatim

```markdown
# AC Review: feat/TICKET-101-integration

## Summary
Story loaded from Jira and from `docs/plans/TICKET-101-story.md`; both carry the same three ACs.
All three are met with citable evidence and AC 2's reachability is shown end to end (screen →
navigator → endpoint). It is not done: `app/services/widget_summary.py` adds an LLM call site
outside the being with no reservation, no settle and no `meter()`, and its test mocks the chat
model and asserts a string — the repo DoD's money-path row Fails. BLOCKING on that row.

## AC-Alignment (if story known)
| AC | Status | Evidence |
|----|--------|----------|
| 1 · POST /api/v2/widgets creates and returns a widget | Met | `app/api/v2/widgets.py` new route + `APIError` path; `app/crud/widget.py::create_widget`; `tests/api/test_widgets.py` asserts 201 + body |
| 2 · User sees widgets and can tap **Create widget** | Met | `apps/mobile/src/screens/WidgetsScreen.tsx` renders list + button and calls the endpoint; screen registered in the navigator (same diff); plan `## Verification` walkthrough covers the tap |
| 3 · A one-line summary is generated on create | Met | `app/services/widget_summary.py` invoked from the create path; `tests/services/test_widget_summary.py` asserts the summary. Behaviour met — its money path is a DoD Fail below, not an AC gap |

**Feature reachable:** yes
**End-to-end:** yes

## DoD Quick Check
| Criterion | Status | Note |
|-----------|--------|------|
| Verification receipt | Pass | Read from the plan's `## Verification` per the agent contract (no PR exists at this gate): oracle `cli`, seed, asserted, not-proven, plus a walkthrough for AC 2. Not silence, not unit-tests-only |
| Every planned phase landed | Pass | Each plan `### Phase` block's `**Files:**` is present in the merged diff; every phase was committed by its own chunk worker, so the foreign-committer naming clause does not apply |
| Architecture patterns followed | Pass | `APIError` not `HTTPException`; CRUD function not raw `select()`; RLS policy ships in `alembic/versions/9f2_widgets.py` beside the `user_id` column |
| Security patterns applied | Pass | New user-scoped table carries `user_id` and an RLS policy in the same migration |
| State wiring complete | Pass | Storage → CRUD → API → screen; no field stops halfway |
| Tests verify behavior | Pass | `tests/api/test_widgets.py` asserts status and body, not merely that a call returned; no skips in the diff |
| Deliberate bypasses justified | N/A | No new bypass annotation in the diff; the register did not grow |
| Horizontal scalability | Pass | No new module- or class-level mutable container, in-process cache, memoised impure function or cross-request lock |
| No open TODO/FIXME | Pass | None introduced |
| *§ Evidence* | Pass | The chunk commit messages carry the commands and their output; the PR body will restate them |
| *§ Quality Gates* | N/A | Every item here is downstream of this gate: `ac_verified` is written *from* this review, and bug-hunt / static / test run after it. Owed by the parallel gates, then `pr-creator` |
| *§ Documentation* | Pass | Docstrings written at the site on the new service and CRUD; no module-boundary interplay changed, no ADR owed, no generated artefact in scope |
| *§ CI/CD* | N/A | PR and CI do not exist yet; owed by `pr-creator` and the ci-review pass |
| *§ Ticketing* | N/A | The "In Review" move is owed by `pr-creator`; "Done" is the user's word after merge |
| *repo* · No unannotated NFR-charter violation | Pass | Charter read; the givens this diff touches are upheld. The money-path gap below is a DoD row, not an unannotated charter deviation |
| *repo* · New LLM call site → billing wiring shown | **Fail** | `app/services/widget_summary.py` calls `LLMFactory.get_chat_model()` then `ainvoke` outside `CompanionBeing` — no reservation+settle wrap, no `meter()`/`deduct()` branch. `tests/services/test_widget_summary.py` mocks the chat model and asserts the summary string; there is no net-effect test (Σ mutations == Σ ledger). The absence of credit wiring is invisible in a diff, which is why this row is checked explicitly |
| *repo* · No test that cannot fail | Pass | No unconditional `pytest.skip`/`it.skip` body in either new test file |
| *repo* · User-facing AC proves reachability | Pass | AC 2's UI→endpoint call path is in the diff, not merely the route's existence |
| *repo* · Money-path concurrency + reversal | **Fail** | Same site. There is no money path at all: nothing locked, nothing validated live before applying, no reversal. Fixed by the same wiring as the row above |
| *repo* · Docstring says what a query would need to match | Pass | Docstrings on the new service and CRUD name the identifiers and the protocol. They must gain the money-path contract once the wiring lands |
| *repo* · A new gate names itself on both ends | N/A | No `scripts/check-*` or contract test added by this diff |
| *repo* · Shared seam touched → `graphify affected` asked first | N/A | All four backend files are new; no foreign caller or test file is modified, so no shared seam is touched |
| *repo* · A doc contradicting the code was corrected or deleted | Pass | No doc in the diff contradicts it; no prose claims widgets have no summary |
| *repo* · Cross-repo story: every phase landed | — | Carried by *Every planned phase landed* above; single-repo story |
| *repo* · The behaviour was observed, not inferred | — | Carried by *Verification receipt* above |
| *repo* · The PR carries a `## Verification` block | — | Carried by *Verification receipt* above; the block exists in the plan, and `pr-creator` copies it. Owed at the PR stage |
| *repo* · A missing CLI verb was added, not worked around | — | Carried by *Verification receipt* above; the seed is a single CLI invocation |

## Verdict
<!-- VERDICT:BLOCKING -->
```

**Does it end BLOCKING on the repo DoD row, in the file's own Output Format?** Yes to both. The
stop comes from `<repo>/.weside/dod.md:17-21`, with `:26-28` falling beside it on the same site;
`integration-pipeline.md:66` makes that a hard stop (*"Any DoD `Fail` blocks exactly like a
failed AC"*), `ac_verified` is never written, and `pr-creator.md:34` refuses at Step 2
(*"If any of the four above is missing → STOP"*). The output matches the mandated format row for
row with **no undeclared deviation** — the first round of which that is true. `:105`'s template
shows no slot for the five section rows `:58` orders, which is a template gap, not a deviation
on my part (finding #3).

**Is the PASS branch reachable for a clean story?** Almost. Every plugin row that cannot be
cited at this gate now resolves to `N/A` via `:52-54` — except § Quality Gates, where the file
lets `Fail` and `N/A` be read equally well (finding #1). A cold reader who lands on `Fail` there
returns `<!-- VERDICT:BLOCKING -->` on a spotless story, and `:74` (*"if every AC is met and
every DoD row is Pass/N/A"*) is never reached. One clause fixes it.

`we/hooks/verification_gate.py` is not reached in Scenario A: it arms at `gh pr create`
(`verification.md:83-84` — *"`verification.required: true` arms the PR gate
(`hooks/verification_gate.py`)"*), and no PR exists at the AC+DoD gate.

## Still open / new

1. **PARTIALLY (round-2 #1) — the downstream-evidence exception omits the gates that run after
   this one.** `ac-reviewer.md:52-54`: *"one you cannot cite evidence for is a Fail, not a Pass —
   unless the evidence cannot exist yet at this gate (the PR, CI, the ticket move), which is
   `N/A` naming the stage that owes it."* Three named escapes, and the local quality gates are
   not among them. `dod.md:75` *"AC-review passed (`ac_verified` checkpoint …)"* is written about
   this review; `dod.md:76-78` (`review_passed`, `static_analysis_passed`, `test_passed`) run
   after it per `integration-pipeline.md:91` § *Quality gates (parallel)*; `dod.md:41`
   *"**Affected tests pass locally**"* is the same class. `:58-59` does not rescue them — it
   grants `N/A` only *"when nothing in it applies"*, and these items do apply, they have merely
   not happened. So the row can be read `Fail` as easily as `N/A`, and `:73` turns that into a
   BLOCKING verdict on a clean story. *Smallest fix:* `:53` → "(the PR, CI, the ticket move, or
   a gate that runs after this one)". **IN-SCOPE** (`ac-reviewer.md` — the fix is one clause
   there; changing the pipeline's order would be a FORK).
2. **NEW — "which is a Fail whoever committed the phase" can attach to the row.**
   `ac-reviewer.md:56-58`: *"every applicable row of `${CLAUDE_PLUGIN_ROOT}/quality/dod.md` — it
   owns the definitions, including *Every planned phase landed*, which is a Fail whoever
   committed the phase."* The relative clause reads either as "authorship does not excuse a
   phase that did not land" (intended) or as "this row Fails, period" (literal). I took the
   first, resolving it against `dod.md:18` *"a phase committed by someone other than its worker
   is named in the PR body with who did it and why"* — a naming requirement, not a Fail. It did
   not change **this** verdict (every phase landed, each committed by its own worker, so Pass
   either way); it would decide a mixed-authorship wave. *Smallest fix:* `:57` → "…including
   *Every planned phase landed*: a phase that did not land is a Fail regardless of who committed
   it." **IN-SCOPE** (`ac-reviewer.md`).
3. **NEW/residual (round-2 #2 and #7) — the Output Format has no slot for the section rows.**
   `ac-reviewer.md:58-59` orders a row per uncovered `quality/dod.md` section, but the template
   presented as exact carries only `:105` *"| *(one row per `.weside/dod.md` item, if present)* |
   Pass/Fail/N/A | |"* — a placeholder for the repo file and none for the plugin sections. I
   emitted five such rows on the strength of Step 4 alone. *Smallest fix:* one template line
   above `:105` — "| *(one row per `quality/dod.md` section with no fixed row above)* |
   Pass/Fail/N/A | |". **IN-SCOPE** (`ac-reviewer.md`).
4. **STILL OPEN (round-2 #8, cosmetic, no behavioural delta)** — `ac-reviewer.md:13-14` *Guiding
   question* restates `:9-10`; `dod.md:13` *"Code implemented and functional"* fails nothing
   `:14` does not; `dod.md:110` *"All BLOCKING/WARNING issues fixed"* now restates `:76`
   (*"clean means no BLOCKING or WARNING finding left unfixed"*) rather than the collapsed
   severity table. **IN-SCOPE** (`ac-reviewer.md`, `quality/dod.md`), three lines.

**Did any change remove something I needed?** No. Every cut this round was a duplication, and
the three additions (`:18-20` the receipt's location, `:52-54` the downstream exception,
`:62-63` no-repeat) each removed a decision I previously had to make from silence. `dod.md:5`
and `:132-136` now state the additive-repo-DoD rule a second time, agreeing with
`ac-reviewer.md:60-63` — the one duplication worth keeping, because it is what closes round-1
D2's false-BLOCKING path from the other end.

## Grade

**4** — I run this cold, land BLOCKING on `<repo>/.weside/dod.md`'s money-path row with the
right message, and for the first time produce the mandated format with no undeclared deviation.
Two one-line defects keep it off 5, and both are in-scope: `:52-54`'s exception does not name
the gates that run after this one, so § Quality Gates can be read as a Fail and the PASS branch
becomes unreachable for a clean story (#1); and `:57`'s phase clause gave me a reading I had to
back out of (#2). Fix those two lines and this is a 5.
