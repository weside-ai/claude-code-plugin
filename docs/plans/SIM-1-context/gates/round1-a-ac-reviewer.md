---
type: simulation-report
chunk: gates
scenario: A — ACs met, one repo DoD row violated
round: 1
grade: 3
---
# Round 1 · Scenario A

I am `we:ac-reviewer`, spawned once at integration against the full merged diff of
`TICKET-101` on `feat/TICKET-101-integration`. Everything below is traced, not executed.

## Trace

**0 — What I load before Step 1.** My own file only. Nothing in `ac-reviewer.md` tells me to
read `.weside/config.json`, `references/verification.md`, `references/ticketing.md` or
`references/integration-pipeline.md`. I know from the frontmatter that a plugin DoD exists at
`${CLAUDE_PLUGIN_ROOT}/quality/dod.md` because Step 4 names it; I do **not** know that
`review.available`, `ticketing.tool` or `verification.required` exist. This matters twice below.

**1 — Step 1, branch + ticket key.**
`Bash("git rev-parse --abbrev-ref HEAD")` → `feat/TICKET-101-integration`.
Regex `[A-Z]+-[0-9]+` → `$TICKET = TICKET-101`. Clean; the key is second in the branch, and
`pr-creator.md:30-31` promises it is first (`{type}/{TICKET}-description`) — here that holds by
luck of the naming, not by the rule.

**2 — Step 1, "load the story from the ticketing tool".** Here I hit the first fork the file
does not resolve. `ac-reviewer.md:28-30` names no tool, no detection order, and no pointer —
`pr-creator.md:94` points at `references/ticketing.md` for exactly this and my file does not.
The world's config says `ticketing.tool: "jira"`, but I was never told to read that file. My
tool listing shows Jira MCP tools as *deferred* — I would have to
`ToolSearch("select:mcp__atlassian__jira_get_issue")` first, then
`jira_get_issue(issue_key="TICKET-101")`. **Which way I went and why:** I skipped the ticketing
call. The next clause gives me a concrete file path, that path exists, and the ACs live in it;
spending a schema fetch plus a network call to re-fetch the same three ACs from a tool I was
never told I have is not worth the round trip. A weaker model that reads clause one literally
and finds no tool has no instruction for what to do next — the file has no else-branch.

**3 — Step 1, plan.** `Read("docs/plans/TICKET-101-story.md")` → hits. I get the three ACs and a
complete `## Verification` (oracle `cli`, seed, asserted, not-proven, plus a walkthrough note
for AC 2). Note the path convention collides with `worker-dispatch.md:51`, which tells workers
the plan is a *directory* (`docs/plans/<story>/`). Two files in one plugin, two shapes. Mine
won because it is the one I was told to read; the legacy fallback `${TICKET}-plan.md` was not
needed.

**4 — Step 2, the diff.** `Bash("git status --porcelain")` → empty (the Lead merged and
committed three chunk branches; nothing dirty). So the second clause: derive the base.
`Bash("gh pr view --json baseRefName")` → **fails**, no PR exists yet — at integration the PR is
five steps downstream (`integration-pipeline.md:152-166`). Fall back as instructed:
`Bash("git symbolic-ref refs/remotes/origin/HEAD")` → `origin/main`. Then
`Bash("git merge-base --fork-point origin/main HEAD")` and
`Bash("git diff <base>...HEAD --stat")`, then the full `git diff <base>...HEAD` per file. I get
the eight files of the merged diff. **Review the DIFF, not entire files** — so for
`app/services/widget_summary.py` I read the added hunk, which is the whole file (it is new).

**5 — Step 3, previous reviews.** `Glob(".reviews/*")` → no such directory. Not a delta review;
this is V1. (I note for Step 5 that the branch name contains a `/`.)

**6 — Step 4, ACs.** Each AC gets its own row, each with a citation. All three have one.

**7 — Step 4, reachable / end-to-end.** AC 2 says the user can *see* and *tap*. I check the
UI→endpoint call path inside the diff: `WidgetsScreen.tsx` calls `POST /api/v2/widgets` and the
screen is registered in the navigator, both in the diff. Reachable: yes. End-to-end: yes.

**8 — Step 4, plugin DoD.** `Read("${CLAUDE_PLUGIN_ROOT}/quality/dod.md")` → available, so the
"otherwise apply the four criteria" fallback never fires. I now hold ~50 checkboxes across ten
sections and an Output Format table with **seven** fixed rows. The mapping is undefined (Defect
3). I fill the seven rows and let the rest inform them.

**9 — Step 4, the Verification item.** `ac-reviewer.md:17-20` tells me this check is mine alone
and that a missing block is BLOCKING. `quality/dod.md:34` says the block is carried by **the
PR** — and there is no PR. **Which way I went and why:** I treated the plan's `## Verification`
section as the receipt, because Step 1 put that file in my hands and it holds a complete block.
That is the right answer, and I reached it without the file telling me — nothing in
`ac-reviewer.md` names the location (Defect 2). Then I discover I have nowhere to put it: the
Output Format table has no Verification row (Defect 1). I add one, deviating from the mandated
format, because reporting a BLOCKING-capable check as prose only is worse than a format
deviation.

**10 — Step 4, repo-local DoD.**
`Bash("git rev-parse --show-toplevel")` → the repo root.
`Bash("test -f <root>/.weside/dod.md && echo yes")` → yes. `Read("<root>/.weside/dod.md")`.
**Which way I went and why:** the bullet is headed "*(additive, **optional**)*"
(`ac-reviewer.md:55`), which reads as a licence to skip. I did not skip, because the body of the
same bullet says "ADDITIVE to the plugin DoD above, **never** a replacement" and
`quality/dod.md:5` says the agent "reads it additively — both the checklist below and the repo
file apply". Two of three statements are mandatory; "optional" loses. **This is the single
choice the whole scenario turns on** (Defect 4) — a reader who honours the word "optional" never
opens the file, and `app/services/widget_summary.py` sails through.

I count **13** checkbox items in the extension (6 NFR + 4 documentation + 3 verification) and
add one row each, per `ac-reviewer.md:58` ("one row per repo-local item"). "Item" is undefined —
checkbox or section? I chose checkbox; section would have given 3 rows and buried the finding
inside a lumped "NFR Charter" verdict.

**11 — The finding.** Repo row 2: *"New LLM call site → billing wiring shown — a diff that adds
an LLM call site outside `CompanionBeing` demonstrates its money path (reservation+settle wrap
OR the `meter()` `deduct()` branch) and ships/extends a net-effect test (Σ mutations == Σ
ledger)."* Against the diff: `app/services/widget_summary.py` calls
`LLMFactory.get_chat_model()` then `ainvoke`, with no reservation, no settle, no `meter()`; and
`tests/services/test_widget_summary.py` asserts the summary string over a mocked chat model —
no ledger assertion. **Fail.** Nothing in `quality/dod.md` names this class; the extension does.
Its own note is exactly why I found it — "the ABSENCE of credit wiring is invisible in a diff;
reviewers check for it explicitly."

**12 — Rows I could not answer from evidence.** Repo row 1 (NFR charter) needs
`docs/architecture/NFR-CHARTER.md`, whose contents no step gives me and which
`ac-reviewer.md` never tells me to fetch. Repo row 9 (`graphify affected` was asked *before* the
change) is a claim about a past action that leaves no artefact in a diff — unfalsifiable here.
Plugin "Migrations run and reverse" needs a local apply I have no receipt for; "Index column
order" names no index. **Which way I went and why:** I marked each `N/A` with its reason rather
than `Pass`. `ac-reviewer.md:47` demands a citation per **AC** and says nothing about DoD rows —
so the file's own no-citation-no-pass standard is silent exactly where I would otherwise have to
guess, and a guessed `Pass` on an NFR row is the failure this whole agent exists to prevent
(Defect 5).

**13 — Step 5, save.** The mandated path is `.reviews/<YYYYMMDD-HHMM>_<branch>_V<n>.md`. My
branch contains a slash, so the literal name is
`.reviews/20260827-1430_feat/TICKET-101-integration_V1.md` — a nested directory, not a file in
`.reviews/` (Defect 6). **Which way I went and why:** I wrote
`.reviews/20260827-1430_feat-TICKET-101-integration_V1.md`, substituting `-` for `/`, because
the stated *reason* for the format ("so the directory sorts chronologically") is defeated by the
literal reading. Undeclared deviation number two.
*(In this table-top run I execute nothing and create no `.reviews/` file; this is the call I
would have made.)*

**14 — Step 6, verdict.** One DoD row Fails → `<!-- VERDICT:BLOCKING -->`.

### The verdict I would have written, verbatim

```markdown
# AC Review: feat/TICKET-101-integration

## Summary
All three acceptance criteria are met with citable evidence, and AC 2's reachability is shown
end to end (screen → navigator → endpoint), so the story does what was asked. It is not done:
`app/services/widget_summary.py` adds an LLM call site outside the being with no reservation,
no settle and no `meter()`, and its test mocks the chat model and asserts a string — the repo
DoD's money-path row fails. Verdict is BLOCKING on that one row; everything else is Pass or a
stated N/A.

## AC-Alignment (if story known)
| AC | Status | Evidence |
|----|--------|----------|
| 1 · POST /api/v2/widgets creates and returns a widget | Met | `app/api/v2/widgets.py` new route + `APIError` path; `app/crud/widget.py::create_widget`; `tests/api/test_widgets.py` asserts 201 + body |
| 2 · User sees widgets and can tap **Create widget** | Met | `src/mobile/src/screens/WidgetsScreen.tsx` renders the list and the button, calls the endpoint; screen registered in the navigator (same diff); plan `## Verification` walkthrough covers the tap |
| 3 · A one-line summary is generated on create | Met | `app/services/widget_summary.py` invoked from the create path; `tests/services/test_widget_summary.py` asserts the summary string. Behaviour met — its money path is a DoD Fail below, not an AC gap |

**Feature reachable:** yes
**End-to-end:** yes

## DoD Quick Check
| Criterion | Status | Note |
|-----------|--------|------|
| Architecture patterns followed | Pass | `APIError` not `HTTPException`; CRUD function not raw `select()`; RLS policy ships in `alembic/versions/9f2_widgets.py` beside the `user_id` column |
| Security patterns applied | Pass | New user-scoped table carries `user_id` + an RLS policy in the same migration |
| State wiring complete | Pass | Storage → CRUD → API → screen; no field stops halfway |
| Tests verify behavior | Pass | `tests/api/test_widgets.py` asserts status and body, not merely that a call returned; no skips anywhere in the diff |
| Verification (observed, not inferred) | Pass | Receipt read from the plan's `## Verification` (no PR exists yet at integration): oracle `cli` + seed + asserted + not-proven, plus a walkthrough for AC 2. Not silence, not unit-tests-only |
| Deliberate bypasses justified | N/A | No new `# *-BYPASS-OK:`-style annotation anywhere in the diff; the register did not grow |
| Horizontal scalability | Pass | No new module- or class-level mutable container, in-process cache, memoised impure function or cross-request lock in the diff |
| No open TODO/FIXME | Pass | None introduced |
| *repo* · No unannotated NFR-charter violation | N/A | Cannot be checked from here — the charter's contents were not available to this review. Flagged rather than passed |
| *repo* · New LLM call site → billing wiring shown | **Fail** | `app/services/widget_summary.py` calls `LLMFactory.get_chat_model()` then `ainvoke` outside `CompanionBeing` with no reservation+settle wrap and no `meter()`/`deduct()` branch. `tests/services/test_widget_summary.py` mocks the chat model and asserts the summary string — there is no net-effect test (Σ mutations == Σ ledger). A ledger row is not billing; absence of credit wiring is invisible in a diff, which is why this row is checked explicitly |
| *repo* · No test that cannot fail | Pass | No unconditional `pytest.skip` / `it.skip` body in either new test file |
| *repo* · User-facing AC proves reachability | Pass | AC 2's UI→endpoint call path is in the diff, not merely the route's existence |
| *repo* · Money-path concurrency + reversal | **Fail** | Same site. There is no money path at all, so there is nothing locked, nothing validated live before applying, and no reversal. Falls with the row above and is fixed by the same wiring |
| *repo* · Cross-repo story: every phase landed | N/A | Single-repo story; the plan names no second repo |
| *repo* · Docstring says what a query would need to match | Pass | Docstrings were written on the new service and CRUD. Note: they must gain the money-path contract once the wiring above lands |
| *repo* · A new gate names itself on both ends | N/A | No `scripts/check-*` or contract test added by this diff |
| *repo* · Shared seam touched → `graphify affected` asked first | N/A | Not checkable from a diff — the question leaves no artefact. Flagged, not passed |
| *repo* · A doc contradicting the code was corrected or deleted | Pass | No doc in the diff contradicts it; no prose claims widgets have no summary |
| *repo* · The behaviour was observed, not inferred | Pass | Oracle `cli` against a running DEV instance per the repo recipe, plus a browser walkthrough for AC 2's tap |
| *repo* · The PR carries a `## Verification` block | Pass (at this stage) | Complete in the plan. `pr-creator` must copy it into the PR body; if it does not, this row flips |
| *repo* · A missing CLI verb was added, not worked around | Pass | The receipt's seed is a single CLI invocation, not a shell dance |

## Verdict
<!-- VERDICT:BLOCKING -->
```

## Which gate stops what, with which message

This scenario ends **BLOCKING**, and it is stopped by the *repo extension*, not the plugin: the
row **"New LLM call site → billing wiring shown"** from `<repo>/.weside/dod.md`, with the
sentence *"`app/services/widget_summary.py` calls `LLMFactory.get_chat_model()` then `ainvoke`
outside `CompanionBeing` with no reservation+settle wrap and no `meter()`/`deduct()` branch, and
no net-effect test."* A second repo row (money-path concurrency + reversal) falls with it and is
fixed by the same wiring. Downstream, `integration-pipeline.md:66` turns that into a hard stop
("Any DoD `Fail` blocks exactly like a failed AC"), so `ac_verified` is never written and
`pr-creator.md:39` refuses at Step 2. **But the stop is conditional on one word:** if the
reviewer honours "*(additive, **optional**)*" and skips the extension, every remaining row
passes, the verdict is PASS, and a new unbilled LLM call site ships. Nothing in the plugin DoD
would have caught it.

## Defects

1. **The one check the agent calls "yours alone" has no row in its own mandated output.**
   `we/agents/ac-reviewer.md:17-20`: *"**One check is yours alone:** the DoD's *Verification*
   items… A `## Verification` block that is missing, or that only names unit tests, is a
   BLOCKING finding."* The Output Format's DoD Quick Check (`ac-reviewer.md:98-108`) lists
   Architecture, Security, State wiring, Tests, Bypasses, Scalability, TODO — and no
   Verification row. The most emphasised, explicitly BLOCKING-capable check in the file has
   nowhere to be recorded, so a compliant output can be silent about it while the verdict claims
   completeness. I deviated from the format to add the row. *Smallest fix:* add
   `| Verification receipt present (oracle named, not tests-only) | Pass/Fail/N/A | |` to the
   table at `ac-reviewer.md:104`.

2. **The Verification block's location is never named, and both wrong resolutions are
   reachable.** `ac-reviewer.md:19` says "A `## Verification` block that is missing… is a
   BLOCKING finding" without saying *where* it lives. The only authority the agent is told to
   load, `we/quality/dod.md:34`, says *"**The PR** carries a `## Verification` block — oracle,
   seed, what was asserted, what stays unproven. No block, no claim of verified."* At
   integration there is no PR — the PR is created five steps later
   (`integration-pipeline.md:152`). The file that resolves this
   (`we/references/integration-pipeline.md:81-83`, *"write the `## Verification` block now into
   the story plan's `## Verification` section… `pr-creator` copies it into the PR body"*) is
   never referenced from `ac-reviewer.md`. Two wrong landings are available: a false BLOCKING
   ("no PR body, therefore no block") or a false N/A ("no PR yet, skip"). *Smallest fix:*
   `ac-reviewer.md:19` → "…in the story plan's `## Verification` section at integration, or the
   PR body once a PR exists".

3. **A seven-row fixed table is asked to express a ~50-checkbox DoD, with no mapping.**
   `ac-reviewer.md:51-54` — *"**DoD Quick Check:** Architecture compliance, security, wiring,
   test depth (see `${CLAUDE_PLUGIN_ROOT}/quality/dod.md` if available…)"* — while
   `quality/dod.md` carries ten sections including Documentation (7 items), Post-Implementation
   Semantic Checks (11), Evidence, Quality Gates and Ticketing, none of which has a row. In this
   scenario the plugin DoD's own "Feature REACHABLE" (`dod.md:17`) and its Documentation cascade
   (`dod.md:87-106`) were only checked because the *repo* file happens to duplicate them — take
   the extension away and neither appears in the output. *Smallest fix:* state the rule
   explicitly at `ac-reviewer.md:51` — "one row per `quality/dod.md` **section**, plus one row
   per repo-local item; a section with nothing applicable gets one N/A row with its reason."

4. **"optional" is the word that decides whether this scenario is caught.**
   `ac-reviewer.md:55`: *"**Repo-local DoD additions (additive, optional):**"*. It contradicts
   its own next sentence ("ADDITIVE to the plugin DoD above, never a replacement") and
   contradicts `quality/dod.md:5` ("the `we:ac-reviewer` agent reads it additively — both the
   checklist below and the repo file apply") and `integration-pipeline.md:64-66` ("both apply,
   the repo file adds and never replaces"). The word was presumably meant as "the *file* is
   optional to exist"; it reads as "the *step* is optional to run", and reading it that way
   turns this BLOCKING into a PASS. *Smallest fix:* `(additive; mandatory when the file exists)`.

5. **No evidence standard for DoD rows, only for ACs.** `ac-reviewer.md:46-47`: *"Each AC
   individually verified against the diff, with evidence (file path, test name, commit) — **no
   item passes without a citation**."* The clause is scoped to ACs. Nothing says what a DoD row
   owes, so the rows that cannot be answered from the diff — the NFR-charter row (charter
   contents never fetched, and no step tells the agent to fetch them), the `graphify affected`
   row (a past action leaving no diff artefact), plugin "Migrations run and reverse", plugin
   "Index column order" — invite a silent `Pass`. Four rows that read green while nothing was
   checked is precisely the failure this agent exists to prevent. *Smallest fix:* extend line 47
   — "…no item passes without a citation; a DoD row with no obtainable evidence is `N/A` with
   the reason, never `Pass`."

6. **The saved-review filename breaks on every branch name the pipeline generates.**
   `ac-reviewer.md:73-74`: *"Write to `.reviews/<YYYYMMDD-HHMM>_<branch>_V<n>.md` — timestamp
   first so the directory sorts chronologically."* Every branch this plugin creates contains a
   slash (`feat/<story>-integration`, `worker-dispatch.md:112`), so the literal path is
   `.reviews/20260827-1430_feat/TICKET-101-integration_V1.md` — a subdirectory, which defeats
   both the stated sort *and* Step 3's flat lookup for a prior review, silently turning every
   delta review into a fresh V1. *Smallest fix:* "`<branch>` with `/` replaced by `-`".

7. **Step 1's ticketing clause is unresourced.** `ac-reviewer.md:28-29`: *"If a key is found →
   load the story from the ticketing tool for the AC check."* No tool named, no detection order,
   no pointer — while `pr-creator.md:94` sends the same lookup to `references/ticketing.md`, and
   `.weside/config.json` (which the agent is never told to read) holds `ticketing.tool`. There
   is also no else-branch: nothing says what to do when neither the tool nor the plan yields
   ACs, while the Output Format hedges with "(if story known)" and Step 4 demands every AC be
   verified. *Smallest fix:* append "— detection per `${CLAUDE_PLUGIN_ROOT}/references/
   ticketing.md`; neither source available → say so in the Summary and mark the AC table
   `unknown`, which is BLOCKING."

8. **Step 2's two branches are exclusive where they should be additive.**
   `ac-reviewer.md:34`: *"Uncommitted work present → the working + staged diff. **Otherwise** the
   diff against the merge base."* At integration a single stray uncommitted file would scope
   this entire review to that file and drop the eight-file merged diff — including
   `widget_summary.py`. It did not fire here (the tree is clean), which is luck, not design.
   *Smallest fix:* "Reviewing a chunk → working + staged diff. Reviewing an integration branch →
   always the merge-base diff, plus any uncommitted work."

9. **A severity table whose two top tiers are indistinguishable.** `quality/dod.md:124-128`
   gives `BLOCKING | MUST fix` and `WARNING | MUST fix` — identical actions under different
   names. Since `ac-reviewer.md:120` also says *"A DoD Fail blocks exactly like an unmet AC — no
   separate severity tiers"*, the distinction has no consumer in this agent at all. *Smallest
   fix:* collapse to two rows, `MUST fix` / `Fix or document skip reason`.

## Cuttable lines (no-ops for an Opus-class model)

1. `ac-reviewer.md:64-69` — the whole **"Horizontal scalability (server-side diffs)"** paragraph,
   *"new process-local mutable state that outlives a request is a Fail unless annotated with
   `# SCALABILITY-EXEMPT: <reason>`… in-process caches, module- or class-level mutable
   containers, memoisation on non-pure functions, in-process locks…"* — a near-verbatim
   restatement of `quality/dod.md:59-62`, which this agent is told to load two bullets earlier.
   Six lines duplicated between the exact two files under measurement; the behaviour survives on
   the `dod.md` copy alone, and the output-table row at `:106` keeps it visible.
2. `ac-reviewer.md:60-63` — the **"Deliberate-bypass compliance"** paragraph, *"each new
   `# *-BYPASS-OK:`-style annotation needs a *specific* reason — 'legacy' and 'TODO' are not
   reasons…"* — same duplication against `quality/dod.md:25-28`. Same argument, same survival.
3. `ac-reviewer.md:52-54` — *"if available, otherwise apply the four criteria: architecture
   patterns followed, security patterns applied, state wiring complete, tests verify behaviour"*
   — a fallback that cannot fire for a plugin-installed agent whose `${CLAUDE_PLUGIN_ROOT}`
   resolves, and if it ever did, the four criteria are already the first four rows of the Output
   Format table three sections below.
4. `ac-reviewer.md:118` — *"- Review the **diff**, not entire files"* — verbatim duplicate of
   `ac-reviewer.md:37`, *"**Review the DIFF, not entire files.**"*, already emphasised in bold at
   the point of use. One of the two is free.
5. `ac-reviewer.md:121` — *"**ALWAYS save to file** before outputting verdict"* — Step 5 (save)
   is numbered before Step 6 (verdict). The sequence already says this; a model that skips Step 5
   is not one this line rescues.
6. `ac-reviewer.md:122` — *"Not your job: bug-hunting, security-vuln-hunting, code style — that's
   the bug-hunt engine…"* — the third statement of the same boundary, after the frontmatter
   description (*"Does not hunt bugs (that's Codex adversarial-review…)"*, `:3`) and
   `:10-12` (*"This agent never hunts bugs — bug-hunting runs separately…"*).
7. `ac-reviewer.md:14-15` — *"**Guiding question:** Does this diff actually satisfy what was
   asked — and is it done, not just built?"* — restates the Purpose sentence directly above it
   (`:9-10`). Nice framing; zero behavioural delta.
8. `quality/dod.md:29`, `:63`, `:106` — *"Not applicable → skip if no architecture constraints in
   plan"*, *"**Not applicable** → skip when the item has nothing to do with this change"*,
   *"Nothing above applies → skip"* — three renderings of "skip what does not apply", each
   formatted as a **checkbox**, which then pollutes any per-item row count. Deleting all three
   changes nothing; keeping them as prose costs one line instead of three checkboxes.
9. `quality/dod.md:44-45` — *"Verify each item that applies; skip the rest."* — the same
   instruction a fourth time, one line above item `:63` that says it again.
10. `quality/dod.md:16` — *"- [ ] Code implemented and functional"* — nothing can fail this that
    the acceptance-criteria rows two lines below do not already fail. It is a header wearing a
    checkbox.
11. `quality/dod.md:113` — *"- [ ] All BLOCKING/WARNING issues fixed"* — restates the Issue
    Severity table at `:124-128`, whose own two top rows are already indistinguishable (Defect 9).
12. `quality/dod.md:3` vs `:144` — *"**A story is DONE when all criteria below are met.**"* and
    *"A story is DONE when every applicable box above is ticked"* — the same sentence opening and
    closing the file. The second adds "awaiting the user's merge", which is the only part worth
    keeping.

## What I needed and did not find

1. **Where the `## Verification` block lives at integration time.** The plan holds it; my file
   never says so, and the DoD it sends me to says "the PR". I inferred it.
2. **How to reach the ticketing tool.** No name, no detection pointer, no instruction to read
   `.weside/config.json`, and the Jira tools are deferred behind a `ToolSearch` I was never told
   to run.
3. **The mapping from `quality/dod.md`'s ~50 checkboxes to seven table rows.** I invented one.
4. **Whether "one row per `.weside/dod.md` item" means checkbox or section.** I chose checkbox
   (13 rows). Section would have produced 3 rows and buried the money-path Fail inside a lumped
   NFR verdict.
5. **What evidence a DoD row owes**, and what to write when none is obtainable. I chose `N/A`
   with a stated reason over `Pass`; nothing in either file backs that choice.
6. **The NFR charter's contents.** Repo DoD row 1 cannot be checked without them and no step
   fetches them, so the row is structurally unanswerable from this agent's context.
7. **Any way to check "`graphify affected` was asked before the change."** It is a claim about a
   past action with no diff artefact — an item a diff reviewer can never falsify.
8. **A branch-name sanitisation rule for the review filename**, and whether `.reviews/` should be
   gitignored (an unignored review directory turns every future diff noisy).
9. **What to do when I deviate from the mandated Output Format.** I did so twice (added a
   Verification row, sanitised the filename). The file has no channel for saying so, and its
   Output Format is presented as exact.

## Grade

**3** — I land on the right verdict with the right message, but only because I overrode the word
"optional" that guards the very file carrying the finding, and I had to invent the Verification
row, the checkbox-vs-section reading, the DoD evidence standard and the filename escaping to get
there; a careful run that reads any one of those the other way ships an unbilled LLM call site
with a green table.
