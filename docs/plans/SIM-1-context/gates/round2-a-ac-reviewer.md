---
type: simulation-report
chunk: gates
scenario: A — ACs met, one repo DoD row violated
round: 2
grade: 4
---
# Round 2 · Scenario A

I am `we:ac-reviewer`, dispatched once at integration against the full merged diff of
`TICKET-101` on `feat/TICKET-101-integration`. Nothing is executed; every tool call is traced.

## Verdict on round 1

| # | Round-1 finding | Verdict | Evidence (quoted revised line + file:line) |
|---|---|---|---|
| D1 | The Verification check has no row in the mandated output | **FIXED** | `we/agents/ac-reviewer.md:91` — `\| Verification receipt \| Pass/Fail \| Oracle + seed + asserted + not-proven, or `not-applicable` with its reason \|`, and `:18` *"It is the first row of your table and it Fails like any other"*. `:19-20` also settles the round-1 ambiguity about `not-applicable`: *"`not-applicable` with a stated reason is a Pass; silence is not."* |
| D2 | The `## Verification` block's location is never named | **STILL OPEN** | `ac-reviewer.md:18-19` still reads *"a `## Verification` block that is missing, or that only names unit tests, is BLOCKING"* — no location. The only authority the agent is told to load still says `we/quality/dod.md:34` *"**The PR carries a `## Verification` block**"*, and at the AC gate no PR exists (`we/references/integration-pipeline.md:152` puts PR creation five steps later). The line that resolves it, `integration-pipeline.md:80-82` (*"write the `## Verification` block now into the story plan's `## Verification` section … `pr-creator` copies it into the PR body"*), is still never referenced from `ac-reviewer.md`. `pr-creator.md:68` now names the location precisely (*"copied verbatim from `docs/plans/${TICKET}-story.md` § Verification"*) — but `pr-creator` is not a file this agent reads. A false BLOCKING ("no PR body → no block") is still reachable. |
| D3 | A fixed table asked to express a ~50-checkbox DoD, no mapping | **PARTIALLY** | The table grew to nine fixed rows plus a repo slot (`ac-reviewer.md:91-100`), and Step 4 is now explicit: `:55` *"every applicable row of `${CLAUDE_PLUGIN_ROOT}/quality/dod.md`"*. But the mapping is still unstated and now **asymmetric**: repo items get *"its own row"* (`:58`) while ~50 plugin checkboxes across Testing, Post-Implementation Semantic Checks, Evidence, Quality Gates, Documentation and Ticketing must land in nine fixed rows or nowhere. See *Still open / new* #2. |
| D4 | *"(additive, **optional**)"* — the word the scenario turned on | **FIXED** | `ac-reviewer.md:56-58` — *"when `<repo-root>/.weside/dod.md` exists (`git rev-parse --show-toplevel`) — every applicable row of that file too. The repo file is **additive and mandatory when it is there**, never a replacement; give each of its items its own row. No such file → skip silently."* The detection command is inline, the licence to skip is gone, and no other file contradicts it. This is the single change that makes Scenario A land the same way on a careful cold run as on mine. |
| D5 | No evidence standard for DoD rows, only for ACs | **FIXED — and it overshot** | `ac-reviewer.md:50-51` — *"no item passes without a citation, and each AC gets its own row. The same standard binds every DoD row: one you cannot cite evidence for is a Fail, not a Pass."* The silent-`Pass` hole is closed, and it correctly forces the NFR-charter fetch instead of licensing an N/A. The overshoot is a new defect — *Still open / new* #1. |
| D6 | Saved-review filename breaks on every branch the pipeline generates | **FIXED** | `ac-reviewer.md:62-63` — *"`/` in the branch name replaced by `-` so the file lands in `.reviews/` itself."* Residual (not a finding): Step 3's read side, `:44` *"Look for an earlier review for this branch under `.reviews/`"*, does not restate the sanitisation, but a flat directory and a loose lookup no longer disagree. |
| D7 | Step 1's ticketing clause is unresourced, and has no else-branch | **FIXED** | `ac-reviewer.md:28-31` — *"load the story from the ticketing tool (detection: [`ticketing.md`](../references/ticketing.md)) … No key, or no ticketing tool → review against the plan alone and say which in the Summary."* Both halves of the round-1 complaint are answered: a pointer, and an else-branch. |
| D8 | Step 2's two branches exclusive where they should be additive | **FIXED** | `ac-reviewer.md:36-38` — *"Include the working + staged diff when the tree is dirty; on an integration branch the merge-base diff is the review, never one stray uncommitted file."* The exact failure (one stray file scoping away the eight-file merged diff, `widget_summary.py` included) is now named and forbidden. |
| D9 | A severity table whose two top tiers are indistinguishable | **STILL OPEN — and it lost its last reader** | `quality/dod.md:127-128` is unchanged: `\| **BLOCKING** \| MUST fix \|` and `\| **WARNING** \| MUST fix \|`. The revision added `dod.md:122-123` in prose — *"there is no second, softer tier for 'only' the DoD"* — and deleted `ac-reviewer.md`'s Rules section, so the table now has **no consumer in the reviewing agent at all** while the prose above it asserts the opposite of what a two-tier table implies. See *Still open / new* #5. |
| C1 | Cut the duplicated Horizontal-scalability paragraph | **FIXED** | Gone from `ac-reviewer.md`; the definition survives once at `quality/dod.md:59-62` (a file Step 4 orders read) and stays visible as row `ac-reviewer.md:98`. No reversal — I did not need the second copy. |
| C2 | Cut the duplicated Deliberate-bypass paragraph | **FIXED** | Gone; survives at `quality/dod.md:26-29`, visible as row `ac-reviewer.md:97`. No reversal. |
| C3 | Cut the unreachable "otherwise apply the four criteria" fallback | **FIXED** | `ac-reviewer.md:55` is now bare: *"every applicable row of `${CLAUDE_PLUGIN_ROOT}/quality/dod.md`"*. Considered as a reversal candidate: the cut leaves no else-branch if the plugin DoD is unreadable, where the repo file got one (`:58` *"No such file → skip silently"*). Not a finding — the plugin file ships with the plugin. |
| C4 | Duplicate *"Review the diff, not entire files"* | **FIXED** | One copy left, at the point of use: `ac-reviewer.md:40` *"**Review the DIFF, not entire files.**"* |
| C5 | *"ALWAYS save to file before outputting verdict"* | **FIXED by merge** | The standalone Rules line is gone; the clause is folded into Step 5 as `ac-reviewer.md:64` *"Save the file before you output the verdict."* Net one line, and it now sits where it acts. |
| C6 | Third statement of the not-your-job boundary | **FIXED** | The Rules line is gone. Two statements remain — frontmatter `:3` (the tool-listing description, which is a different audience) and `:10-11` *"This agent never hunts bugs — that is the separate bug-hunt pass"*. |
| C7 | The Guiding question restates Purpose | **STILL OPEN** | `ac-reviewer.md:13-14` — *"**Guiding question:** Does this diff actually satisfy what was asked — and is it done, not just built?"* — still directly under `:9-10`. Cosmetic; zero behavioural delta either way. |
| C8 | Three "skip what does not apply" checkboxes polluting the item count | **FIXED** | The standalone checkboxes are gone. What remains is one prose line, `quality/dod.md:46` *"Verify each item that applies; skip the rest."*, and one clause folded into the item it governs, `:29` *"No such convention → skip."* Nothing is a checkbox any more, so the per-item row count is clean — which matters directly, because `ac-reviewer.md:58` counts items. |
| C9 | *"Verify each item that applies"* stated a fourth time | **FIXED** | One copy: `quality/dod.md:46`. |
| C10 | *"Code implemented and functional"* — a header wearing a checkbox | **STILL OPEN** | `quality/dod.md:13` unchanged, one line above `:14` *"Acceptance Criteria individually verified"*, which fails everything it could fail. |
| C11 | *"All BLOCKING/WARNING issues fixed"* restates the severity table | **STILL OPEN** | `quality/dod.md:110` unchanged; falls with D9. |
| C12 | The DONE sentence opening and closing `dod.md` | **FIXED** | Only `quality/dod.md:3` remains — *"**A story is DONE when all criteria below are met.**"* The file now closes on `:133-137` § *Who checks this*, which routes rather than repeats. |

Round-1 § *What I needed and did not find*, re-judged compactly: #2 (ticketing route), #3/#4 (item = checkbox, via `:58`), #5 (DoD evidence standard), #8 (filename escaping) are now **answered in the file**. #1 (where the receipt lives), #7 (`graphify affected` unfalsifiable — but see #1 below, it resolves on *applicability*, not evidence) and #9 (no channel for declaring a deviation from the mandated Output Format) are **still open**. #6 (NFR-charter contents) is **answered** — `:51` makes the fetch compulsory and the repo row carries the link, so I now `Read` the charter instead of shrugging.

## Trace on the revised files

**0 — What I load.** My own file. It names three resources by path: `references/ticketing.md`
(`:29`), `${CLAUDE_PLUGIN_ROOT}/quality/dod.md` (`:55`) and `<repo-root>/.weside/dod.md` with
its detection command (`:56`). Round 1 had one. Not named: `.weside/config.json`,
`references/verification.md`, `references/integration-pipeline.md`.

**1 — Step 1, branch + key.** `Bash("git rev-parse --abbrev-ref HEAD")` →
`feat/TICKET-101-integration`. Key `TICKET-101`.

**2 — Step 1, the ticketing tool.** A key is present, so `:29` sends me to detection:
`Read("we/references/ticketing.md")` → priority order, weside MCP first, Atlassian MCP second.
The Jira tools are deferred, so `ToolSearch("select:mcp__atlassian__jira_get_issue")`, then
`jira_get_issue(issue_key="TICKET-101", comment_limit=20)` — `ticketing.md:12` makes comments
part of the fetch. **This is a behaviour change from round 1**, where I skipped the ticketing
call because the clause was unresourced. The ticket's ACs match the plan's three.

**3 — Step 1, the plan.** `Read("docs/plans/TICKET-101-story.md")` → three ACs and a complete
`## Verification` (oracle `cli`, seed, asserted, not-proven, plus a walkthrough note for AC 2).
I read the plan's `### Phase` blocks here too, for `:53`.

**4 — Step 2, the diff.** Derive the base, never assume `main`:
`Bash("gh pr view --json baseRefName")` → fails, no PR exists at the AC gate; fall to
`Bash("git symbolic-ref refs/remotes/origin/HEAD")` → `origin/main`.
`Bash("git status --porcelain")` → clean. `Bash("git diff origin/main...HEAD --stat")` then the
full per-file diff. Eight files. `:37-38` means I would not have been derailed even by a dirty
tree — the round-1 trap is closed, not merely unfired.

**5 — Step 3, previous reviews.** `Glob(".reviews/*")` → nothing. V1, not a delta review.

**6 — Step 4, ACs.** Three rows, each with a citation. AC 2's reachability: `WidgetsScreen.tsx`
calls `POST /api/v2/widgets` and the screen is registered in the navigator, both inside the
diff — the UI→endpoint path, not the route's existence.

**7 — Step 4, phases landed.** `:53-54`. I compare each plan `### Phase` block's `**Files:**`
against the eight changed files. Three chunk branches merged and nothing in the diff contradicts
the plan's file lists → Pass.

**8 — Step 4, plugin DoD.** `Read("${CLAUDE_PLUGIN_ROOT}/quality/dod.md")`. Nine fixed rows in
the Output Format cover Verification, phases, architecture, security, wiring, tests, bypasses,
scalability, TODO. The rest of the file — Testing, Post-Implementation Semantic Checks,
Evidence, Quality Gates, Documentation, Ticketing — has no row (finding #2).

**9 — Step 4, the Verification receipt.** It is *"the first row of your table"* (`:18`). Where
does the block live? `ac-reviewer.md` does not say, and `quality/dod.md:34` says the PR, which
does not exist. **Which way I went and why:** the plan's `## Verification` section, because
Step 1 put that file in my hands and it holds a complete block. Same inference as round 1, from
the same silence — D2 is unfixed.

**10 — Step 4, repo DoD.** `Bash("git rev-parse --show-toplevel")` → repo root.
`Read("<root>/.weside/dod.md")`. No decision to make this time: `:57` says *additive and
mandatory when it is there*. I count 13 checkbox items (6 NFR-class + 4 documentation-class +
3 verification-class) and write 13 rows per `:58`. Four of those duplicate fixed rows above
(finding #3).

**11 — The finding.** Repo row: *"**New LLM call site → billing wiring shown** — a diff that
adds an LLM call site outside `CompanionBeing` demonstrates its money path (reservation+settle
wrap OR the `meter()` `deduct()` branch) and ships/extends a net-effect test (Σ mutations == Σ
ledger)"* (`<repo>/.weside/dod.md:17-21`). Against the diff: `app/services/widget_summary.py`
calls `LLMFactory.get_chat_model()` then `ainvoke` with no reservation, no settle, no `meter()`;
`tests/services/test_widget_summary.py` mocks the chat model and asserts the summary string —
no ledger assertion. **Fail.** Nothing in `quality/dod.md` names this class.

**12 — Rows I cannot cite from the diff.** `:51` now says a row I cannot cite evidence for is a
**Fail**. It bites correctly on the NFR charter — the repo row carries the charter's path, so I
`Read("docs/architecture/NFR-CHARTER.md")` rather than shrug, and answer it. It does not bite on
`graphify affected`: all four backend files are new, no foreign caller is modified, no shared
seam is touched, so the row is not *applicable* under `:55` → N/A on applicability, not on
evidence. It bites wrongly on the lifecycle rows (`dod.md:108-116`, `:40`) — finding #1. I mark
those N/A with the stage that owes them. **That is my one undeclared deviation this round**
(round 1 had two).

**13 — Step 5, save.** `.reviews/20260827-1430_feat-TICKET-101-integration_V1.md`, which is now
the literal instruction, not a repair. *(Traced only; I create no file.)*

**14 — Step 6, verdict.** DoD rows Fail → `<!-- VERDICT:BLOCKING -->`.

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
| 2 · User sees widgets and can tap **Create widget** | Met | `src/mobile/src/screens/WidgetsScreen.tsx` renders list + button and calls the endpoint; screen registered in the navigator (same diff); plan `## Verification` walkthrough covers the tap |
| 3 · A one-line summary is generated on create | Met | `app/services/widget_summary.py` invoked from the create path; `tests/services/test_widget_summary.py` asserts the summary. Behaviour met — its money path is a DoD Fail below, not an AC gap |

**Feature reachable:** yes
**End-to-end:** yes

## DoD Quick Check
| Criterion | Status | Note |
|-----------|--------|------|
| Verification receipt | Pass | Read from the plan's `## Verification` (no PR exists at this gate): oracle `cli`, seed, asserted, not-proven, plus a walkthrough for AC 2. Not silence, not unit-tests-only |
| Every planned phase landed | Pass | Each plan `### Phase` block's `**Files:**` is present in the merged diff across the three chunk branches |
| Architecture patterns followed | Pass | `APIError` not `HTTPException`; CRUD function not raw `select()`; RLS policy ships in `alembic/versions/9f2_widgets.py` beside the `user_id` column |
| Security patterns applied | Pass | New user-scoped table carries `user_id` and an RLS policy in the same migration |
| State wiring complete | Pass | Storage → CRUD → API → screen; no field stops halfway |
| Tests verify behavior | Pass | `tests/api/test_widgets.py` asserts status and body, not merely that a call returned; no skips in the diff |
| Deliberate bypasses justified | N/A | No new bypass annotation anywhere in the diff; the register did not grow |
| Horizontal scalability | Pass | No new module- or class-level mutable container, in-process cache, memoised impure function or cross-request lock |
| No open TODO/FIXME | Pass | None introduced |
| *repo* · No unannotated NFR-charter violation | Pass | Charter read; the givens this diff touches are upheld. The money-path gap below is a DoD row, not an unannotated charter deviation |
| *repo* · New LLM call site → billing wiring shown | **Fail** | `app/services/widget_summary.py` calls `LLMFactory.get_chat_model()` then `ainvoke` outside `CompanionBeing` — no reservation+settle wrap, no `meter()`/`deduct()` branch. `tests/services/test_widget_summary.py` mocks the chat model and asserts the summary string; there is no net-effect test (Σ mutations == Σ ledger). Absence of credit wiring is invisible in a diff, which is why this row is checked explicitly |
| *repo* · No test that cannot fail | Pass | No unconditional `pytest.skip`/`it.skip` body in either new test file |
| *repo* · User-facing AC proves reachability | Pass | AC 2's UI→endpoint call path is in the diff, not merely the route's existence |
| *repo* · Money-path concurrency + reversal | **Fail** | Same site. There is no money path at all: nothing locked, nothing validated live before applying, no reversal. Falls with the row above and is fixed by the same wiring |
| *repo* · Cross-repo story: every phase landed | N/A | Single-repo story; the plan names no second repo |
| *repo* · Docstring says what a query would need to match | Pass | Docstrings written on the new service and CRUD; they name the identifiers and the protocol. They must gain the money-path contract once the wiring lands |
| *repo* · A new gate names itself on both ends | N/A | No `scripts/check-*` or contract test added by this diff |
| *repo* · Shared seam touched → `graphify affected` asked first | N/A | Not applicable: all four backend files are new, no foreign caller or test file is modified, so no shared seam is touched |
| *repo* · A doc contradicting the code was corrected or deleted | Pass | No doc in the diff contradicts it; no prose claims widgets have no summary |
| *repo* · The behaviour was observed, not inferred | Pass | Covered by the *Verification receipt* row above: oracle `cli` against a running DEV instance, plus a walkthrough for AC 2 |
| *repo* · The PR carries a `## Verification` block | Pass (at this stage) | Complete in the plan. `pr-creator` copies it into the PR body; if it does not, this row flips |
| *repo* · A missing CLI verb was added, not worked around | Pass | The receipt's seed is a single CLI invocation, not a shell dance |

## Verdict
<!-- VERDICT:BLOCKING -->
```

**Does it end BLOCKING on the repo DoD row, in the file's own Output Format?** Yes to both. The
verdict is stopped by `<repo>/.weside/dod.md`'s *"New LLM call site → billing wiring shown"*,
with *"Money-path concurrency + reversal"* falling beside it on the same site;
`integration-pipeline.md:66` turns that into a hard stop (*"Any DoD `Fail` blocks exactly like a
failed AC"*), `ac_verified` is never written, and `pr-creator.md:34` refuses at Step 2. The
output matches the mandated format row for row, with a single deviation: two rows carry `N/A`
where `:51` demands `Fail` (finding #1). Round 1 needed two deviations and one overridden word
to get here.

`we/hooks/verification_gate.py` exists but Scenario A never reaches it: it arms at
`gh pr create` (`verification.md:84` — *"`verification.required: true` arms the PR gate
(`hooks/verification_gate.py`)"*), and no PR is created at the AC+DoD gate.

## Still open / new

1. **NEW — the Fail-not-Pass rule makes every review BLOCKING forever.** `ac-reviewer.md:51`:
   *"The same standard binds every DoD row: one you cannot cite evidence for is a Fail, not a
   Pass."* Several plugin DoD rows cannot be cited at this gate **by construction**, because
   they are downstream of it in `integration-pipeline.md`'s own checkpoint order:
   `quality/dod.md:108` *"PR created (pr_created checkpoint)"*, `:109` *"CI passed or reviews
   green"*, `:114` *"Ticket moved to 'In Review'"*, `:115` *"User reviewed and merged"*, and
   `:40` *"Coverage meets project thresholds (verified by CI on push — not a local gate)"*. Read
   literally, each is a Fail, and `:68` (*"`<!-- VERDICT:BLOCKING -->` if any AC is unmet or any
   DoD row Fails"*) then returns BLOCKING on every story that will ever be reviewed — the PASS
   branch at `:69` becomes unreachable. The rule also contradicts the format it must fill:
   `:93-100` still offers `Pass/Fail/N/A`, and `:69` treats N/A as passing. *Smallest fix:*
   `:51` → "…a Fail, not a Pass — unless the evidence cannot exist yet at this gate, then `N/A`
   naming the stage that owes it." **IN-SCOPE** (`ac-reviewer.md`).
2. **STILL OPEN — plugin items get nine fixed rows, repo items get one row each.**
   `ac-reviewer.md:55` orders *"every applicable row of `${CLAUDE_PLUGIN_ROOT}/quality/dod.md`"*
   checked, but the Output Format gives fixed rows for nine classes only, while `:58` gives the
   repo file *"its own row"* per item. So `quality/dod.md`'s Documentation cascade (`:86-104`,
   seven items), Post-Implementation Semantic Checks (`:49-62`, eleven), Evidence (`:69`),
   Testing (`:39-42`) and Ticketing have nowhere to be recorded. In this scenario that is
   harmless only because the repo file happens to re-state the documentation and verification
   classes; take the extension away and neither appears in the output. *Smallest fix:* one
   clause at `:55` — "a `quality/dod.md` section with no fixed row above gets one row, N/A with
   its reason when nothing in it applies." **IN-SCOPE** (`ac-reviewer.md`).
3. **NEW — `:58` forces the same check to be written four times.** *"give each of its items its
   own row"* has no exception for an item a fixed row already covers. In this run the receipt is
   recorded once as fixed row `:91` *Verification receipt* and again as three repo rows (*The
   behaviour was observed*, *The PR carries a `## Verification` block*, *A missing CLI verb was
   added*); fixed row `:92` *Every planned phase landed* is re-stated by the repo's *Cross-repo
   story: every phase landed*. Four redundant rows dilute a table whose whole job is to make one
   Fail visible. *Smallest fix:* append to `:58` — "skip a repo item a fixed row above already
   covers, naming which row carries it." **IN-SCOPE** (`ac-reviewer.md`).
4. **STILL OPEN — the receipt's location (round-1 D2).** Restated here because it is the only
   remaining path to a *wrong* verdict rather than a noisy one: `ac-reviewer.md:18-19` names no
   location, and the one authority it loads, `quality/dod.md:34`, names the PR, which does not
   exist at this gate. *Smallest fix:* `:19` → "…in the story plan's `## Verification` section
   at integration, or the PR body once a PR exists." **IN-SCOPE** (`ac-reviewer.md`; the
   alternative fix — pointing at `integration-pipeline.md:80-82` — would be a FORK).
5. **STILL OPEN — a severity table with two identical rows and no reader left.**
   `quality/dod.md:127-128`: `| **BLOCKING** | MUST fix |` and `| **WARNING** | MUST fix |` —
   identical actions under different names. The revision deleted `ac-reviewer.md`'s Rules
   section, so nothing in the reviewing agent consumes the table any more, while
   `quality/dod.md:122-123` asserts in prose *"there is no second, softer tier for 'only' the
   DoD"*. The prose is the rule; the table is a leftover that implies a tier the prose denies.
   *Smallest fix:* collapse to two rows, `MUST fix` / `Fix or document skip reason`.
   **IN-SCOPE** (`quality/dod.md`).
6. **STILL OPEN — a DoD item about the plan, checked against a diff.** `quality/dod.md:19`:
   *"**Parallelisation considered** — for stories with 3+ independent implementation phases:
   `parallel_groups` is set in the plan frontmatter, or there is an explicit note in the plan
   explaining why phases must be sequential."* At the AC gate the workers have already run in
   whatever shape the plan chose; a Fail here is unactionable, and there is no row for it in the
   Output Format. It belongs to the DoR scan, not to a diff reviewer. *Smallest fix:* move the
   item to `references/dor-scan.md`, or mark it "checked at DoR, not at the AC gate".
   **IN-SCOPE** (`quality/dod.md`) for the annotation; moving it is a FORK.
7. **STILL OPEN — no channel for declaring a deviation from the mandated Output Format.** The
   format at `:75-104` is presented as exact, and `:51` forces one deviation in this very run
   (two `N/A`s where the rule says `Fail`). *Smallest fix:* one line under Step 6 — "a row you
   could not fill as specified says so in its Note." **IN-SCOPE** (`ac-reviewer.md`). If #1 is
   fixed, this one disappears with it.
8. **STILL OPEN (cosmetic, no behavioural delta):** `ac-reviewer.md:13-14` *Guiding question*
   restates `:9-10`; `quality/dod.md:13` *"Code implemented and functional"* fails nothing that
   `:14` does not; `quality/dod.md:110` *"All BLOCKING/WARNING issues fixed"* restates the
   severity table in #5. **IN-SCOPE**, three lines.

**Did any cut remove something I needed?** No. The scalability and bypass paragraphs and the
four-criteria fallback all survive where Step 4 sends me (`quality/dod.md:59-62`, `:26-29`), and
the rows at `ac-reviewer.md:97-98` keep them visible. The revision is shorter *and* steered me
better: three named resources instead of one, one undeclared deviation instead of two, and the
extension opened without an argument.

## Grade

**4** — I run this cold and land BLOCKING on the right repo row with the right message, and the
word the whole scenario turned on is fixed (`:57`, *"additive and mandatory when it is there"*).
Two things keep it off 5: the receipt's location is still unnamed while the only DoD I load says
"the PR", so a false BLOCKING at integration remains reachable; and `:51` read literally Fails
five rows that are downstream of this gate by construction, which would bury the money-path
finding in a table where everything is red.
