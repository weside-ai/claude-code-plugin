# SIM-1 · `/we:ci-review` · Round 3 · Scenarios A + C

**Table-top simulation. Nothing was executed; no file was written except this one.**

Skill under test: `we/skills/ci-review/SKILL.md`, **291 lines** (round 2: 285). All line numbers
below are the **new** file's; round-2 quotes are marked as such.
Round-2 reports: `round2-scenario-a.md`, `round2-scenario-c.md`.
Authoring contract: `.claude/rules/plugin-authoring.md`.

Method note: every **FIXED** below is backed by text that the round-2 reports quoted as absent or
different. Text round 2 already quoted verbatim is treated as pre-existing and gets no credit.

---

## Scenario A trace

PR #3721, base `main`. `codex-review` red (run 9911), no comment. Zero threads.
`coderabbitai[bot]`: "Actionable comments posted: 0". `claude[bot]`: `VERDICT:PASS`, no `SEV:`.
User: *"codex ist rot, mach mal /we:ci-review"* — no flag.

**Step 0 — routing.** L25-26 defines `--ci-only`; nothing says a pure-CI complaint routes there by
itself, and the frontmatter (L3-7, byte-identical to round 2) carries no trigger for it. I run the
full path. Same outcome here.

**Step 1 — the gate (L17-23).** L20 now reads *"read it with `gh pr checks $PR --required`, never
from memory (drop the flag to see the advisory checks too)"*.

- `Bash: gh pr checks 3721 --required` → the required set; `codex-review` is in it, red.

This command lives only in the intro paragraph. No phase step owns it — 1b's source 1 (L96) is
still bare `gh pr checks $PR`. I run it because L20 says "never from memory", not because a step
told me to.

**Step 2 — 1a (L64-79).** Fresh-shell warning first (L66-69), now naming both failure modes:
*"An undefined `$REVIEW_ALLOWLIST` matches every login and turns the hard gate into a deadlock; an
undefined `$GH_AVAILABLE` skips the mandatory resolve step in silence."* The derivation block now
**contains** `REVIEW_ALLOWLIST` (L77) — it moved up from 3d.

```bash
gh auth status …            → GH_AVAILABLE=true
PR=…                        → 3721
REPO=…                      → the app repo, OWNER=the host repo-ai, REPO_NAME=the host repo
BASE_REF=…                  → main
REVIEW_ALLOWLIST=…          → "greptile|coderabbit|claude" (fallback; the absence of
                              .weside/config.json is inherited from C's spec for the same repo,
                              not observed in A's)
gh pr view 3721 --json mergeable,mergeStateStatus,autoMergeRequest,state
                            → MERGEABLE / BLOCKED / null / OPEN
```

L84's `CONFLICTING`/`DIRTY` branch does not fire.

**Step 3 — 1b (L91-117).**

- source 1 `gh pr checks 3721` → five rows, `codex-review fail 1m …/runs/9911`. L97's comment
  ("keep the run URL column, 1c consumes it") marks the URL as live input.
- source 2 graphql (now selecting `databaseId`, L102), `-F pr=3721 …` → **empty**.
- source 3 → `=== coderabbitai[bot] ===` / "Actionable comments posted: 0". No rows.
- source 4 → the `VERDICT:PASS` body, no `SEV:`. No rows. The shape-not-name filter (L111-113) is
  the correct instrument for the dual-login trap; unchanged from round 2 and still right.

**Step 4 — 1c (L119-137), the section that decides this scenario.**

- `Bash: gh run view 9911 --log-failed` → `remote: HTTP 429` during `actions/checkout`, then
  `VERDICT:ERROR`.
- Classify per L134-136: checkout/network HTTP error, job errored without producing a verdict →
  **re-run**, do not change code.
- `Bash: gh run rerun 9911 --failed`.

**Step 5 — 1d (L139-155).** One row:
`| 1 | CI (codex-review) | — | BLOCKING | — | runner: checkout 429, VERDICT:ERROR | — | re-run fired |`
No human threads. Note L147: *"matches `$REVIEW_ALLOWLIST` (see 3d)"* — the variable now lives at
L77 in **1a**, not 3d. Stale pointer (New defect 1).

**Step 6 — 1e (L157-163).** Nothing was pending at collection; the re-run I just fired now is. 1e is
written about the initial long-check window, and no line instructs me to watch a re-run. I
`gh pr checks 3721 --watch` on my own judgment.

**Step 7 — Phase 2 (L168-174).** Not all three conditions hold (a required check is red). I do not
stop. The catastrophic round-1 false green remains impossible.

**Step 8 — Phase 3.**

- **3a (L181-183)** — nothing to accumulate.
- **3b (L185-190)** — I would run `/we:static` + `/we:test` over an **empty** changed surface. No
  guard. Unchanged from round 2.
- **3c (L192-196)** — **new final sentence:** *"Nothing changed (every finding skipped, or the red
  was a re-run) → no commit; continue at 3d."* This is exactly my case, named. No phantom
  `nothing to commit` / HEAD-did-not-move panic. Works.
- **3d (L198-223)** — L208 *"Re-derive the 1a variables at the top of this block"*, plus L66-69's
  standing instruction. I prepend the derivation, `GH_AVAILABLE=true`, `$THREADS` empty, loop is a
  no-op **for the right reason**. Round 2's silent no-op is gone.
- **3e (L226-237)** — L228 *"re-deriving `$REVIEW_ALLOWLIST` exactly as 1a does"*. Count 0, gate
  passes. Then the checklist at L234-237: item 1 is *"every BLOCKING/WARNING row is Fixed or
  Skipped-with-evidence"*. My BLOCKING row is neither — it is **re-run**. Item 1 is unsatisfiable
  for the disposition 1c just made (New defect 2 / N3 half-landed).
- **3f (L239-245)** — no migration; I still test that myself.
- **3g (L247-255)** — (a) now reads *"each failure is fixed, **re-run**, or documented as
  skipped"*. Satisfied. (b) hinges on the checklist item above. (c) n/a. Nothing was committed, so
  `git push` is a no-op; no line says to skip it. Harmless.

**Step 9 — Phase 4/5.** Watch until `codex-review` concludes: green → terminal state 1 (L273-276,
`autoMergeRequest` null so nothing fires by itself); red the same way → 1c's "report it as
infrastructure and stop" = terminal state 3 (L278-279). Both correct. No phase owns the waiting,
and no budget bounds it. Report per Phase 5 (L286-291).

**Net A:** zero code changes, one re-run, no false green, no false push — same correct landing as
round 2, reached with one fewer improvisation (3c) and one fewer silent hole (3d).

---

## Scenario C trace

PR #3725, base `feat/TICKET-000-integration`, 9 files Python+TS. `claude-review` red. Five unresolved
threads. Newest claude comment: SEV:BLOCKING (factually wrong), SEV:WARNING (real),
SEV:SUGGESTION, `VERDICT:BLOCKING`. No `.weside/config.json`. User: `/we:ci-review`.

**Step 1 — gate + 1a.** `gh pr checks 3725 --required` → `claude-review` is required and red.
1a block: `PR=3725`, `BASE_REF=feat/TICKET-000-integration` (from the PR, not assumed `main`),
`REVIEW_ALLOWLIST` → jq on a missing `.weside/config.json` → fallback `greptile|coderabbit|claude`,
`mergeable MERGEABLE` / `mergeStateStatus BLOCKED` → L84 does not fire.

**Step 2 — 1b source 1 + 1c.** `claude-review: fail` → `gh run view <id> --log-failed` → the run
posted successfully; the failure **is** the verdict. 1c's bullets (L134-137) offer "a review verdict
that never posted → BLOCKING row" and "the runner → re-run". Neither is this case. **The skill still
never states that a red review gate and its comment are one finding** (round-2 C defect 5). I
collapse them unaided and do **not** fire `gh run rerun`. A literal reader of L119 opens a second
row here.

**Step 3 — 1b source 2.** The graphql query now selects `databaseId` (L102):

| # | login | bot? | path:line | text | databaseId |
|---|---|---|---|---|---|
| T1 | `coderabbitai[bot]` | yes | `service.py:88` | refactor suggestion | ✔ collected |
| T2 | `coderabbitai[bot]` | yes | `useThing.ts:41` | ⚠️ potential issue | ✔ |
| T3 | `coderabbitai[bot]` | yes | `test_service.py:12` | nitpick | ✔ |
| T4 | `github-actions[bot]` | yes | `service.py:120` | claude inline | ✔ |
| T5 | `maintainer` | **no** | `service.py:60` | "das war Absicht, siehe ADR" | ✔ |

Round 2 had to re-query GitHub for these ids. Now they arrive in the primary collection.

**Step 4 — sources 3 + 4.** Source 3 → the CodeRabbit walkthrough (context). Source 4's shape filter
returns the newest claude comment under either login → 3 `SEV:` rows + `VERDICT:BLOCKING`.

**Step 5 — 1d, human thread first.** L154-155 *"Surface human-authored threads to the user NOW,
before fixing"* → I quote T5 verbatim to the user before touching code, and note it sits on the same
file as the disputed BLOCKING. The skill still never says whether to **wait** for the answer.

Findings table: 8 rows (3 SEV + 4 threads + the human thread). Row "T4 inline" and SEV row 1 restate
the same claim; **no dedupe rule** (round-2 C defect 6), so I carry both.

**Step 6 — the dispute.** I read `service.py`, confirm `await apply_tenant_scope(db, uid)` three
lines above the write. The BLOCKING is false. L40-42's good/bad pair fixes the format (file:line
citation, not a test name). L44-48 gives the destination:

```bash
gh pr comment 3725 --body "Disputed BLOCKING (claude-review): 'target_ref written without
tenant filter'. False — the call site applies apply_tenant_scope(db, uid) at
apps/backend/app/services/service.py:115, three lines above the write. Not changing the code;
this PR needs a human gate override."
```

**Step 7 — fix, validate, commit.** Fix the WARNING (missing escalation target), the SUGGESTION
(rename), T2 (useEffect dep), T3 (unused import). Skip T1 with a reason. Validate per L185-190:
9 files < ~50, no test-config change → affected-only against `BASE_REF`; `/we:static`, `/we:test`,
plus existing `scripts/check-*.sh`. One commit (L192-196), subject `fix: address CI and review
findings`, `TICKET-000` in the body. Verify HEAD moved.

**Step 8 — 3d, the round-2 friction that is gone.** Re-derive 1a's variables (L208 + L66-69). L202
now says a skipped thread gets the reason as a reply first, *"(its first comment's `databaseId`,
from 1b's query, addresses the replies endpoint)"*, with L205:

```bash
gh api repos/the app repo/pulls/3725/comments/<databaseId>/replies -f body="Skipped: …"
```

So T1 (skipped) and T4 (the dispute, per L46) get replies with the ids **already in hand**, then the
resolve loop runs over T1–T4. T5 (`maintainer`) matches neither `[bot]` nor the allowlist → untouched.
Round 2 had to invent both the call and a second query; it now invents neither.

Residual: L202 mandates a reply only for a **skipped** thread. A *fixed* thread still gets resolved
with no "Fixed in `<sha>`" trace (round-2 C defect 7, half-open).

**Step 9 — 3e.** L228's *"re-deriving `$REVIEW_ALLOWLIST` exactly as 1a does"* replaces round 2's
*"reusing … do not redefine it"*. The pattern is `greptile|coderabbit|claude`, **not** empty, so
`test("";"i")` never fires, `maintainer` is not miscounted, the count is 0 and the gate does not
`exit 1`. **The deadlock that made C's push unreachable is gone.** Checklist L234-237: all four
tick (BLOCKING skipped-with-evidence, evidence posted as a PR comment + T4 reply, 0 unresolved bot
threads, T5 surfaced).

**Step 10 — 3f/3g.** No migration. 3g (a) now reads *"each failure is fixed, re-run, or documented
as skipped"* — `claude-review`'s failure is documented as skipped. No wording conflict left.
`git push`.

**Step 11 — termination.** One pass by default (L55-58). Terminal state 3 (L278-279) names my case:
*"a BLOCKING you skipped as factually wrong: the PR needs a human. Report it as blocked, do not keep
pushing."* I do not enter Phase 4 — and that paragraph still sits **inside** opt-in Phase 4
(round-2 C-N4, still open). Report per Phase 5.

**Net C:** identical correct landing to round 2, reached with **no invented mechanics at all** —
the two places round 2 had to improvise (thread reply, allowlist re-derivation) are both shipped.

---

## Round 2 verdicts

### Scenario A

| # | Round-2 defect | Verdict | Evidence (new line numbers) |
|---|---|---|---|
| A-N1a | 3e's "do not redefine `$REVIEW_ALLOWLIST`" contradicts the fresh-shell rule | **FIXED** | The forbidding clause is deleted. L228: *"re-deriving `$REVIEW_ALLOWLIST` exactly as 1a does"*; the assignment itself moved into 1a at L77. |
| A-N1b | 3d silently no-ops on undefined `$GH_AVAILABLE`/`$PR` | **FIXED** | Round 2's own smallest fix offered two options, the second being *"state at 76 'every block below opens with 1a's derivations'"*. The revision took it: L66-69 *"prepend this derivation to every later block that interpolates one of these variables — the thread blocks in 3d/3e included … an undefined `$GH_AVAILABLE` skips the mandatory resolve step in silence"*, plus L208 *"Re-derive the 1a variables at the top of this block."* Traced at A Step 8: the loop no-ops for the right reason. *Note, not a defect:* the fence at L210-223 still opens on `if [ "$GH_AVAILABLE" = true ]` with no derivation inside it — robustness, and it does not fire. |
| A-N2 | No phase owns waiting on a re-run; no budget for it | **STILL OPEN** | L134-136 is substantively the text round 2 quoted (*"A re-run is not a cycle"*, *"report it as infrastructure and stop"*); the `--watch` sentence round 2 asked for was not added. L157-163 (1e) is still about the initial long checks; L261-263 still defines a cycle as *"one push plus the checks and re-reviews it triggers"*. |
| A-N3 | 3g (a) unsatisfiable for a failure disposed of without a commit | **FIXED at 3g, NOT at 3e** | L249-250: *"every check has concluded and each failure is fixed, **re-run**, or documented as skipped"*. But L234's checklist item still reads *"Fixed or Skipped-with-evidence"* — see New defect 2. |
| A-N4 | Gate = required checks, collector treats every check as blocking; `gh pr checks` can't tell them apart | **PARTIALLY (1 of 3 edits)** | L20 gained `--required`. **Not** applied: L96 is still bare `gh pr checks $PR`; L119 is still *"Every non-pass check is a BLOCKING row"*. Does not bite in either scenario (both reds are required), but the contradiction round 2 named is intact. |
| A-N5 | `--ci-only`'s effect on the 3e checklist undecided | **STILL OPEN** | L26 unchanged: *"skip thread collection and the 3d/3e thread steps"*. Two of L234-237's four items are not thread items. |
| R1-5 | Severity table's exception vs the strict skip criteria disagree | **STILL OPEN** | L32 keeps *"or the red is the runner, not the code (see 1c)"*; L36-39 still lists exactly three criteria with **ONLY when**, no runner slot. |
| R1-6 | No empty-diff branch in Phase 3 | **PARTIALLY** | L196 is new and is exactly my case: *"Nothing changed (every finding skipped, or the red was a re-run) → no commit; continue at 3d."* 3b (L185-190) still has no empty-surface guard, and no line skips 3g's no-op push. |
| R1-7 | Re-run has no owning phase | **STILL OPEN** | Same evidence as A-N2. |
| R1-9 | `$REVIEW_ALLOWLIST` used before definition | **FIXED** | Definition is now at L77, inside 1a, above every consumer. |
| R1-10 | 3b copies `/we:test`'s rules | **STILL OPEN** | L189-190 unchanged: *"derive the base ref (1a), and fall back to the full suite when the diff crosses test config or exceeds ~50 files."* |
| R1-12 | Phase 5 has no checkable completion criteria | **STILL OPEN** | L286-291 is four prose bullets; the only `- [ ]` list in the file is L234-237. |
| R1-14 | Frontmatter: noun-phrase lead, synonym triggers, no `--ci-only` trigger | **STILL OPEN** | L3-7 byte-identical. |

**Do the five targeted fixes work in A's traced run?**
Fresh-shell deadlock: **yes** — 3e's forbidding clause is gone and the allowlist is derived before
use. Reply mechanic/`databaseId`: not exercised (zero threads), but present. 3g's push condition:
**yes** — (a) now admits "re-run", the exact disposition 1c made. `--required`: **partially** — the
gate's own line is fixed, the collector's is not. Phase 3's empty-diff branch: **yes at 3c**
(the commit no longer looks like a hook abort), **no at 3b** (still validates an empty surface).

### Scenario C

| # | Round-2 defect | Verdict | Evidence (new line numbers) |
|---|---|---|---|
| C-N1 | 3e's "do not redefine" deadlocks the hard gate on `maintainer`'s thread | **FIXED** | L228 *"re-deriving `$REVIEW_ALLOWLIST` exactly as 1a does"* + L77's assignment inside 1a + L66-69 naming this exact failure (*"matches every login and turns the hard gate into a deadlock"*). Traced: pattern is non-empty, T5 is not counted, count 0, no `exit 1`. |
| C-N2 | Mandated thread reply has no API call and no collected comment id | **FIXED** | L102 adds `databaseId` to the primary query; L202 *"A skipped thread gets the reason as a reply first (its first comment's `databaseId`, from 1b's query, addresses the replies endpoint)"*; L205 gives the call `gh api repos/$REPO/pulls/$PR/comments/<databaseId>/replies -f body=…`. Nothing is improvised in the traced run. |
| C-N3 | 3g (a) contradicts the skip path | **FIXED** | L249-250 *"each failure is fixed, re-run, or **documented as skipped**"*. C's disputed `claude-review` red satisfies it literally. |
| C-N4 | Terminal states are run-global but nested in opt-in Phase 4 | **STILL OPEN** | L259 is still `## Phase 4: Post-push check (opt-in, or user-budgeted)`; L271 *"Terminal states — every run ends in exactly one"* still sits under it. C never enters Phase 4 and still ends there. |
| C-N5 | The good/bad skip pair is verbatim this scenario | **STILL OPEN (observation)** | L41-42 unchanged (`apply_tenant_scope`, `service.py:85`). Still the file's strongest teaching device; still makes this simulation flattering. |
| R1-1 | Run-scoped vars never derived | **FIXED** | `REVIEW_ALLOWLIST` joined 1a (L77); L66-69 and L208 instruct prepending on every consuming block, which is the option round 2 pre-declared acceptable. Same evidence as A-N1b; the fences still show consumers without producers, which is robustness, not a firing defect. |
| R1-5 | `claude-review: fail` fits neither 1c nor a stated identity with source 4 | **STILL OPEN** | L134-137's bullets are unchanged; no line says a red review gate is not a second finding. I collapse them unaided at Step 2. |
| R1-6 | No dedupe between an inline thread and the summary comment | **STILL OPEN** | L139-155 unchanged in this respect; T4 and SEV row 1 stay two rows. Impact stays low because L46 writes the dispute into T4 anyway. |
| R1-7 | Resolved threads carry no reply recording fix or skip | **PARTIALLY** | L202-205 now ships the skip reply. A **fixed** thread still gets a bare `resolveReviewThread` (L220-222) with no `Fixed in <sha>` trace. |
| R1-12 | Single-owner violations | **PARTIALLY** | Unchanged: human threads are still asserted at L154-155, L207, L229, L237 and L291; L50-53 still restates `finish-first.md` instead of citing it. |
| R1-13 | No phase ends in checkable criteria | **STILL OPEN** | Still exactly one `- [ ]` list (L234-237). |

**Do the five targeted fixes work in C's traced run?**
Fresh-shell deadlock: **yes** — this is the run that round 2 could not finish, and it finishes.
Reply mechanic + `databaseId`: **yes** — both replies (T1, T4) are posted from data source 2 already
returned. 3g's push condition: **yes** — the disputed red is "documented as skipped".
`--required`: **partially**, no effect here. Phase 3's empty-diff branch: not exercised (four real
fixes commit normally).

---

## New defects

### 1. `1d` still points at 3d for a variable that moved to 1a — MINOR (revision-introduced drift)

> `L147:` `**Bot?** = yes if the first comment's`author.login` ends in `[bot]` or matches `$REVIEW_ALLOWLIST`(see 3d).`

The assignment was moved out of 3d into 1a (L77) by this very revision; the cross-reference was not
updated. A reader who follows it lands in 3d and finds only a consumer. Exactly the drift class
`plugin-authoring.md` § *Single owner* exists to prevent — the owner moved, the citation did not.
**Smallest fix:** `(see 1a)`.

### 2. N3's fix landed at 3g and not at 3e — MINOR-MAJOR (fires in scenario A)

> `L249-250:` `(a) every check has concluded and each failure is fixed, re-run, or documented as skipped;`
> `L234:` `- [ ] every BLOCKING/WARNING row is Fixed or Skipped-with-evidence`

3g gained the third disposition; the checklist it references at (b) did not. In scenario A the
single BLOCKING row is disposed of by a **re-run** — so (a) passes and item 1 fails, on the same
finding, three lines apart. It errs safe, but 3g's own condition (b) now makes 3g unsatisfiable for
the case (a) was just widened to admit. In scenario A it costs nothing — nothing was committed, so
the withheld push is a no-op. The run where it bites is a **re-run coexisting with real committed
fixes**, which neither traced scenario covers; that is the run to test the fix against.
**Smallest fix:** L234 → *"every BLOCKING/WARNING row is Fixed, Skipped-with-evidence, or re-run
per 1c"*.

### 3. The gate's command has no owning step — MINOR (mechanics half of A-N4, not an independent find)

> `L20:` `read it with`gh pr checks $PR --required`, never from memory`
> `L96:` `# 1) CI status — keep the run URL column, 1c consumes it` / `gh pr checks $PR`

The one command that answers "which checks gate this PR" appears only in the intro; the Collect
phase runs the un-flagged variant. An agent that starts at Phase 1 never learns the required set.
This is A-N4's unapplied half, restated as a mechanics gap rather than a policy contradiction.
**Smallest fix:** make L96 `gh pr checks $PR --required` and keep the bare call as a second line for
the advisory view, then re-title 1c *"Every non-pass **required** check is a BLOCKING row"*.

### 4. `3c`'s skip clause does not reach `3b` or `3g` — LOW

L196 branches the **commit** on an empty change set but leaves 3b validating an empty surface and
3g pushing an unchanged HEAD. Both are no-ops rather than errors, but L179's ⛔ *"ONE continuous
flow, in order"* means a literal follower runs them.
**Smallest fix:** extend L196 — *"…no commit, skip 3b and 3g; continue at 3d."*

---

## What could still be cut

The ASCII workflow block both round-2 reports named is **gone** (L60 is `---`, L62 is Phase 1).
Net arithmetic: 285 → 291 with ~9 cut lines and ~15 added on mechanics (`databaseId`, the replies
call, L66-69's expanded hazard, L77, L196, L228, L249-250). The cut paid for the fixes — that is the
right trade, and it is the reason the file grew while getting more determinate.

Still duplication, all verified present in the new file:

- **L13 vs L15 vs the frontmatter description** — three statements of "collect, fix, push once" in
  the first fifteen lines. Keep L15. ~1 line.
- **L55-58 vs L261-263** — the one-pass default, its exception list and the user-budget override
  written in full twice. Keep the Phase 4 copy, cite it from L55. ~4 lines.
- **L50-53** — the finish-first paragraph restates the host repo's `.claude/rules/workflows/finish-first.md`,
  an always-loaded rule. One citation line. ~3 lines.
- **L189-190** — the two copied `/we:test` rules, with L188 already naming the owner. ~2 lines and
  one drift surface (R1-10, open since round 1).
- **L168-174 (Phase 2)** — restates L20-23's gate definition. Two sentences, one owner. ~2 lines.
- **L32 vs L36-39** — the severity table's exception column and the strict skip list are the same
  rule twice and still **disagree** (no runner slot in the ONLY-when list). Merging fixes the
  contradiction and saves ~3 lines.
- **L226-232 vs L234-237** — prose gate and checkbox list assert the same conditions; keep the
  checklist, reduce the prose to the `exit 1` mechanic. ~3 lines.
- **L181-183 (3a)** — a heading plus one real rule; fold into 3b. ~2 lines.

Against that, New defects 1-4 need ~3 added lines, and the two standing ambiguities (inline-thread
dedupe, the check↔comment identity) one line each. The file can lose ~18 lines net and gain
determinacy. Phase 5 (L286-291) should also become `- [ ]` items — it is the last phase with no
test for "done", and it is where the human-thread and terminal-state reporting obligations land.

---

## Grades

**Scenario A: 4/5** — the run lands correctly with two fewer improvisations than round 2 (3c names
the empty-change case, 3d no longer no-ops silently), but the re-run it fires is still owned by no
phase and bounded by no budget (A-N2, unchanged text), and the N3 fix reached 3g's condition (a)
while leaving 3e's checklist item unsatisfiable for that same disposition.

**Scenario C: 4.5/5** — every one of round 2's three C-specific defects is genuinely fixed and each
works in the traced run: the allowlist deadlock that made the push unreachable is gone, the mandated
thread reply now ships with its endpoint and the `databaseId` to address it, and 3g's condition
admits a documented skip; the missing half-point is inherited ambiguity, not mechanics — the
terminal state that ends this run still lives inside opt-in Phase 4, the inline-thread/summary
dedupe rule is still absent, and nothing states that a red review gate and its comment are one
finding.
