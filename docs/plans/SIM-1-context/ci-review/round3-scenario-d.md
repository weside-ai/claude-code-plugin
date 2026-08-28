# SIM-1 · ci-review · Round 3 · Scenario D (unattended run until merge)

Table-top simulation. Nothing was executed against GitHub; the one real command
run was `gh pr checks --help` (a read-only capability check on the local CLI,
outside the traced scenario — see verdict C). Skill under test:
`we/skills/ci-review/SKILL.md` (291 lines, was 285, was 335). All line numbers
below are the **291-line** numbering. Authoring contract:
`.claude/rules/plugin-authoring.md`. Repo context: `the host repo`,
the host repo's CI rules file, `.weside/config.json`
(`review.available = ["codex","claude","coderabbit"]`).

User request, verbatim: *"automerge ist aktiviert, mach /ci-review bis der PR
gemerged ist, maximal 3 Runden. Ich bin weg."* — then unreachable.

World: branch `fix/TICKET-000-copy-fix`, PR #3730, base `main`, `gh` authed,
auto-merge (squash) armed.

---

## Trace

### Round 0 — reading the revised skill against the request

Both round-1 forks stayed closed, and round 2's two MAJORs are answered before
the first tool call. Nothing left to reconstruct from the host repo:

- **Budget override** (55–58): *"Re-enter Phase 4 only with a concrete reason
  (…) — **or because the user set a budget** ("bis gemerged, max 3 Runden"): an
  explicit user instruction outranks the default, sets the cap, and defines when
  you may stop."* The last clause is new and it is the one that matters: the
  user's instruction now defines the *stop*, which is what terminal state 1's
  new merge-confirmation branch hangs on.
- **Cycle unit** (261–263): *"One **cycle** = one push plus the checks and
  re-reviews it triggers. Default: stop after the first push and report; when an
  exception applies, loop at most twice — a user-stated budget replaces that
  cap."*

| | push | the checks it triggers | cycle |
|---|---|---|---|
| Round 1 | push #1 | round-2 checks (`claude-review` red) | cycle 1 |
| Round 2 | push #2 | round-3 checks (all green) | cycle 2 |
| Round 3 | — | observation only, tail of cycle 2 | — |

Terminal state 1 fires **inside cycle 2**. The exception cap of 2 already
suffices; the user's 3 never binds under either mapping of "Runde" (see New
defect H).

### Round 1

**1a (66–79).** The block now opens with the fresh-shell rule (66–69) and
carries `REVIEW_ALLOWLIST` (77) — round 2's defect F is gone before I hit it.

```
Bash: gh auth status >/dev/null 2>&1 && GH_AVAILABLE=true || GH_AVAILABLE=false   → true
Bash: PR=$(gh pr view --json number --jq .number)                                 → 3730
Bash: REPO=…  → the app repo ; OWNER=the host repo-ai ; REPO_NAME=the host repo
Bash: BASE_REF=$(gh pr view 3730 --json baseRefName --jq .baseRefName)            → main
Bash: REVIEW_ALLOWLIST=$(jq -r '(.review.available // …) | join("|")' .weside/config.json)
      → codex|claude|coderabbit
Bash: gh pr view 3730 --json mergeable,mergeStateStatus,autoMergeRequest,state
      → MERGEABLE / BLOCKED / {squash} / OPEN
```

`mergeable != CONFLICTING`, so 84–88's conflict branch is inert.
`autoMergeRequest != null` is captured here, which makes terminal state 1
evaluable in round 3.

**The gate, read not remembered (19–23).**

```
Bash: gh pr checks 3730 --required
  → CI Summary fail · claude-review pass · codex-review pass   (the three required)
Bash: gh pr checks 3730
  → + Backend (Test) fail  https://…/actions/runs/<id> · Mobile (Test) pass · (rest pass)
```

`Backend (Test)` is advisory here and `CI Summary` is its red roll-up, so the
gate is red either way — but I now *know* which column is which instead of
inferring it from the host repo's CI rules line 9.

**1b (95–117), sources 2–4.** Threads: one `coderabbitai[bot]` nitpick
("'Änderungen gespeichert' vs 'Gespeichert' — pick one voice"). Reviews: a
CodeRabbit summary body, no new findings. Issue comments, filtered by **shape**
(114–116): `claude[bot]` → `<!-- VERDICT:PASS -->`, zero `SEV:` rows.

**1c (119–137).**

```
Bash: gh run view <run-id> --log-failed
  → tests/mobile/toast.spec.ts:41
    AssertionError: expected 'Gespeichert' to equal 'Änderungen gespeichert'
```

Classified per 131–132 as a real finding, not the runner. No re-run.

**1d (139–155).**

| # | Source | Bot? | Severity | File:Line | Issue | Thread ID | Action |
|---|---|---|---|---|---|---|---|
| 1 | CI · Backend (Test) → CI Summary | — | BLOCKING | tests/mobile/toast.spec.ts:41 | asserts pre-change copy | — | fix |
| 2 | CodeRabbit | yes | NITPICK | src/mobile/…/toast.ts | voice inconsistency | PRRT_kwDO… | fix (finish-first, 50–53) |

The PASS comment yields zero rows (152–155). No human threads, so 155's
surface-to-the-user instruction is inert (it would not have been — see Q4).

**Phase 2 (169–174).** Stop condition fails on row 1.

**3a–3c (181–196).**

```
Edit: tests/mobile/toast.spec.ts   (assertion → 'Änderungen gespeichert')
Edit: src/mobile/…/toast.ts       (unify voice)
Bash: /we:static → green ; /we:test (affected: 2 files) → green
Bash: ls scripts/check-*.sh → run the applicable ones → green
Bash: git add -A && git commit -m "fix: address CI and review findings

TICKET-000" && git log --oneline -1        # HEAD moved
```

**3d/3e (198–237).** Resolve the one bot thread; re-run with `| length` → 0;
four-item checklist (234–237) walked clean. **3f** n/a. **3g (248–255)** → `git push`.

Not a terminal state; the budget is set, so I enter Phase 4 on the skill's own
authority.

### Round 2 (cycle 1's tail, then push #2)

```
Bash (background): gh pr checks 3730 --watch   → all conclude; claude-review = fail
```

Re-collect all four sources. No new threads. Source 4:

```
  → === claude[bot] ===
     "## Code Review
      <!-- SEV:WARNING --> the test now asserts the copy twice …
      <!-- VERDICT:WARNING -->"
```

Row 3 added: `claude-review (comment)` · WARNING · `tests/mobile/toast.spec.ts`
· Thread ID `—` · fix. Severity policy line 33: WARNING → MUST fix; and 22–23
makes the red check a gate failure independently of the comment.

Per 265–266 (*"then run Phase 3 again in full — 3d and 3e included, never a bare
re-push"*) I re-enter 3a–3g, not just "fix and push":

```
Edit: tests/mobile/toast.spec.ts   (drop the duplicated assertion)
Bash: /we:test (affected) → green
Bash: git add -A && git commit -m "fix: address CI and review findings

TICKET-000" && git log --oneline -1
Bash: gh api graphql … reviewThreads … | length   → 0
Bash: git push
```

Push #2 → cycle 2. Cap not reached.

### Round 3 (cycle 2's tail)

```
Bash (background): gh pr checks 3730 --watch      → all pass
Bash: gh pr checks 3730 --required                → CI Summary · claude-review · codex-review all pass
Bash: gh api graphql … reviewThreads …            → 0 unresolved
Bash: gh api repos/…/issues/3730/comments --paginate …  → "<!-- VERDICT:PASS -->"
Bash: gh pr view 3730 --json mergeable,mergeStateStatus,autoMergeRequest,state
      → MERGEABLE / CLEAN / {squash} / OPEN
```

Terminal state 1 (273–276), including its new second sentence:

> Only when the user asked for the merge itself ("bis gemerged") confirm it — `gh pr view $PR --json state,mergedAt` once the gate is green — and report `state: MERGED`. (275–276)

```
Bash: gh pr view 3730 --json state,mergedAt   → state=OPEN, mergedAt=null     ← auto-merge has not fired yet
```

**This is the run's only improvisation.** The scenario merges ~90 s after the
last check concludes; the confirm I am told to fire "once the gate is green"
returns `OPEN` and the skill prescribes no branch for that. I polled again on a
self-chosen cadence (30 s, bounded at 5 minutes) rather than reporting a
green-but-unmerged PR as a merge:

```
Bash: gh pr view 3730 --json state,mergedAt   → state=MERGED, mergedAt=2026-08-27T…
```

**Phase 5 (286–291)** — findings table with Actions, three fix lines, push
status, per-check gate status from `--required`, terminal state 1, 0 unresolved
bot threads, no human threads, plus `state: MERGED` with its timestamp.

### The four questions, answered directly

**1. Does the round-2 WARNING trip "repeat finding → stop and escalate"?** No,
and the skill decides it for me — round 2 had to decide it itself. Line 267–269:
*"**A repeat is the same finding text on the same `file:line` after a fix aimed
at it** … A new finding *caused* by your fix is a new finding: fix it and
continue."* The WARNING fails the first conjunct (round 1's finding at that line
was a CI assertion failure, different text, not a reviewer finding) and matches
the second clause exactly. Two sentences of reading, no judgement call.

**2. What is a cycle, and does the cap bind?** 261: one push plus the checks and
re-reviews it triggers. Scenario D costs 2 cycles; the exception cap is 2 and the
user granted 3. It does not bind — not even if "Runde" is read as an observation
round (3 rounds, satisfied on the last permitted one). See New defect H for the
untranslated unit.

**3. Do I confirm the merge, and how?** Yes — 275–276 now authorises exactly the
call round 2 had to invent, gated on the user having asked for the merge itself,
which this user did. `gh pr view $PR --json state,mergedAt`. What is still mine
to invent is *when to fire it a second time* (New defect G).

**4. Am I ever told to wait for the absent human?** No. The global fallback at
281–282 — *"take the safest branch, record the decision and the open question in
the report, and stop — never expand the budget on your own"* — covers it, and
terminal state 3 (278–279) reports "the PR needs a human" rather than waiting for
one. Two *local* instructions still read as stop-and-wait, both inert here and
neither cross-referenced to 281–282: 155 (*"**Surface human-authored threads to
the user NOW**, before fixing"* — mid-Phase-1, and the sharper of the two, since
it fires before any fix) and 245 (3f's *"say so and ask"*). With one human thread
on this PR, an agent obeying 155 literally would stall at Phase 1 with the user
gone, 126 lines before the rule that unblocks it.

---

## Round 2 verdicts

| # | Round-2 defect | Verdict | Evidence (291-line numbering) |
|---|---|---|---|
| A | "The same finding twice" undefined — the only rule that could end scenario D short of merge | **FIXED** | 267–269: *"**A repeat is the same finding text on the same `file:line` after a fix aimed at it**; that means the fix is not landing where the reviewer looks, so stop and escalate. A new finding *caused* by your fix is a new finding: fix it and continue."* Both halves of round 2's judgement are now made by the file; the loose reading that stopped the run is unavailable. Residue, not a defect: *"same finding text"* is a strict **textual** test, so an LLM reviewer rewording the same complaint escapes it — the definition errs toward looping, bounded by the cap and terminal state 2. That is the right direction for an unattended run. |
| B | Terminal state 1 forbade the merge check the user's instruction asks for | **FIXED** | 275–276 authorises `gh pr view $PR --json state,mergedAt`, gated on *"Only when the user asked for the merge itself ("bis gemerged")"*; 58 supplies the matching clause upstream (*"defines when you may stop"*); 78 adds `state` to the 1a fields. Round 2's *"do not wait for it"* survives only as *"say so and stop"* (274) for the un-asked case, which is correct. What remains is the confirm's timing, not its existence → New defect G. |
| C | `gh pr checks` cannot report which checks are required | **FIXED, verified** | 19–20: *"read it with `gh pr checks $PR --required`, never from memory (drop the flag to see the advisory checks too)"*. `--required` is real — `gh pr checks --help` on gh 2.98.0 lists *"--required  Only show checks that are required"*. The parenthetical also preserves the advisory view, which 1c still needs. This is the one row I did not take from memory. |
| D | "The gate" named two conditions 150 lines apart | **PARTIALLY FIXED** | Phase 2 no longer calls its condition a gate — 171–172 reads *"**All green → STOP** only when all three hold: every required check concluded non-red, zero unresolved threads, zero open SEV findings"*, against 21–22's two-condition gate. The collision of the *word* is gone; the two conditions are still stated separately with no half-sentence tying them ("the stop condition is the gate plus zero open SEV findings"). The `--ci-only` half is untouched → New defect I. |
| E | "Default" stated as both 1 and 2 within three lines | **FIXED** | 262–263 now separates them in one sentence: *"Default: stop after the first push and report; when an exception applies, loop at most twice — a user-stated budget replaces that cap."* No number meets the reader twice. |
| F | `$REVIEW_ALLOWLIST` used in Phase 1, defined in Phase 3 | **FIXED** | The `jq` assignment moved into the 1a block (77), and 66–69 states the fresh-shell rule with its failure mode: *"An undefined `$REVIEW_ALLOWLIST` matches every login and turns the hard gate into a deadlock."* 147 now cites *"(see 3d)"* against a variable that already exists. Small residue → New defect J. |

Carried round-1 items that round 2 left open, re-checked against 291 lines:

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 7 | No merge / terminal-state handling | **FIXED** (was PARTIALLY) | Superseded by verdict B: 78, 273–276. |
| 11 | Frontmatter triggers do not map to distinct branches | **STILL OPEN** | 6–7 still quotes `"/we:ci-review", "fix ci", "fix reviews", "ci failed"`; "fix ci" and "ci failed" both reach the one `--ci-only` branch, against `plugin-authoring.md` 60–61 (*"One trigger per branch … Synonyms that rename a single branch are duplication — cut them"*). The description still opens on a noun phrase, against 58–59 (front-load the leading word). MINOR, unchanged across three rounds. |
| 12 | Completion criteria mostly prose | **PARTIALLY FIXED**, unchanged | 234–237's four `- [ ]` items are still the file's only checklist; Phases 1, 2, 4 and 5 end in prose. |
| 14 | Phase 4 does not name Phase 3's steps | **FIXED** (was PARTIALLY) | 265–266: *"then run Phase 3 again in full — 3d and 3e included, never a bare re-push."* Round 2 had to re-enter 3d/3e on its own reading of 3g's precondition; round 3 is told to. |

Also still true and worth one line: 3e's scripted `exit 1` (228–229) counts
threads only, so an open SEV row is caught by checklist item 234, not by the
gate that stops the push. Unchanged since round 2, correctly diagnosed there.

---

## New defects

### G. The authorised merge confirmation is one-shot against a merge that lands 90 seconds later — MAJOR (fires in scenario D)

> confirm it — `gh pr view $PR --json state,mergedAt` **once the gate is green** — and **report `state: MERGED`** (275–276)

The confirm fires when the gate goes green; auto-merge fires ~90 s after that.
The call therefore returns `state: OPEN, mergedAt: null`, and the sentence
prescribes reporting `MERGED` — the outcome, not the observation. There is no
branch for `OPEN`, no cadence, and no bound. Charitably "once green" is a trigger
rather than a count, which is precisely the problem: the reader must pick, and
the parameter they pick (retry interval, ceiling) is invented. Polling is also
outside the cycle accounting (261), so nothing tells the agent that ten polls
are not ten rounds against the user's budget of three.

This is the residue of a real fix, not its failure: round 2 could not confirm the
merge at all, round 3 confirms it and guesses only the retry shape.

**Smallest fix**, replacing the tail of 276: *"…confirm it after the gate is
green: poll `gh pr view $PR --json state,mergedAt` every 30 s for up to
5 minutes. Report `MERGED` with its timestamp; if it has not fired by then,
report the current `state` and `mergeStateStatus` instead of predicting a merge.
Polls are not cycles."*

### H. The user's unit ("Runden") is never translated into the skill's unit ("cycle") — MINOR (inert here)

262–263 says *"a user-stated budget replaces that cap"* while 261 defines the
cap's unit as a cycle. The user said *"maximal 3 Runden"*, and a "Runde" is
plausibly a push-cycle (scenario D: 2) or an observation round of CI (scenario D:
3). Both clear the budget, so no branch changes here — but the same ambiguity
against a user who says "max 1 Runde" decides whether round 2's WARNING may be
fixed at all. **Smallest fix:** at 263 add *"Translate the user's unit into
cycles explicitly in the report ("3 Runden = 3 cycles") — a round the user counts
is a push, not a check."*

### I. `--ci-only` still makes the gate unevaluable by construction — MINOR (inert here)

> `--ci-only` narrows the run to CI: collect sources 1 and 4 only, skip thread collection and the 3d/3e thread steps, still fix and push. **Everything else is unchanged.** (24–26)

21–22's gate requires *"zero bot review threads are unresolved"* and 171–172's
stop condition repeats it, but under this flag threads are never collected. The
final sentence asserts both conditions still stand, so the flag's user is told to
satisfy a clause they were told to skip. Round 2 raised this inside defect D; the
D fix touched the naming and not this. **Smallest fix:** at 26 write *"Under this
flag the thread clause drops from both the gate (21–22) and the stop condition
(171–172); the report says so."*

### J. The fresh-shell warning names one of the two failure modes of an undefined `$REVIEW_ALLOWLIST` — MINOR (inert here)

68–69 warns it *"matches every login and turns the hard gate into a deadlock"* —
true of 3e's count. In 3d the same empty pattern makes `test("";"i")` match
every author, so the resolve loop sweeps up **human** threads, which 208
(*"Leave every human thread for the user"*) forbids and which is not recoverable
by re-running with the variable set. The louder consequence is the unmentioned
one. **Smallest fix:** *"…matches every login: 3d then resolves human threads
too, and 3e's count never reaches 0."*

---

## What I needed and did not find

Down from two to one, and the survivor is a parameter rather than a semantics
question.

1. **How long to keep looking for a merge that lands after the gate goes green.**
   Not inventable from the file: 275–276 authorises exactly one call and
   prescribes its result, 261's cycle accounting does not cover polls, and the
   user's terminal condition is literally `mergedAt != null` (New defect G). I
   chose 30 s × 5 min; another agent reports a green PR as merged on an `OPEN`
   reading, which is a false report to an absent user.

Round 2's two entries are both closed: the required-check set is readable with
`gh pr checks --required` (19–20, flag verified), and "same finding" is defined
at 267–269.

Explicitly **not** listed, because I would do them unprompted and did:
`gh run view --log-failed`; `--watch` to wait; re-entering 3d/3e in cycle 2 (now
also instructed at 265–266); resolving a one-word nitpick on the seam I touched;
running only affected tests; one commit per cycle; inferring `TICKET-000` from the
branch name.

---

## What could still be cut

291 lines, +6 against round 2 while absorbing five fixes — round 2's largest
proposed cut (the five-step workflow code block, old 62–68) is gone, which paid
for them. What remains is what round 2 already named, minus that block:

- **One invariant, three statements.** 22–23 (*"A red required check that posted
  no finding is still red: the gate is the check's conclusion, not the
  comment"*), 120–121 (*"A red check is a finding even when no bot commented on
  it — the case an empty findings table hides"*), 173–174 (*"An empty findings
  table next to a red check is 1c's case, not this one"*). 173–174 is now a
  citation of its owner, which is correct per `plugin-authoring.md` 14–16; 22–23
  is still a full restatement. Reduce it to a half-clause. **~2 lines.**
- **Lines 13 and 15** — *"Collects findings from CI + reviews, fixes them, and
  pushes once everything is addressed"* and *"Core principle: Fix everything.
  Push once. No leftovers."* remain the same sentence twice, both restating the
  frontmatter. Keep 15. **~2 lines.**
- **The frontmatter's two synonym triggers** (6–7) — verdict 11; cutting "ci
  failed" or "fix ci" shortens always-on context, not just this file.

Explicitly **not** cuttable, unchanged from round 2: 41–43's good/bad skip pair
(required by `plugin-authoring.md` 74–76), 66–69's fresh-shell block
(harness-specific, and its absence caused defect F), 152–155's Thread-ID-"—"
aside (it is what keeps a summary-comment SEV in the findings table), 50–53's
finish-first restatement (a plugin skill cannot cite a host repo's rule).

Net: roughly 6 of 291 lines are duplication, against ~12 of 285 in round 2 and
~35 of 335 in round 1. New defect G's fix costs two lines and is affordable.

---

## Grade

**4.5 / 5** — a fresh Opus agent runs scenario D end to end without a single
judgement the file declines to make: the budget override is explicit and names
the stop, "cycle" is defined and the arithmetic lands inside the cap, the
required set is read with a flag that exists, the round-2 WARNING is
disambiguated as a fix-caused new finding by 268–269 rather than by my reading,
Phase 4 names 3d/3e, and the merge the user left the room for is confirmed by an
authorised call. Not 5 because the run still requires one invented parameter —
the retry cadence after that confirm returns `state: OPEN`, which in this
scenario it always does (New defect G); above round 2's 4 because the residue now
costs one line of guessing rather than a judgement that decided whether the PR
merged at all.
