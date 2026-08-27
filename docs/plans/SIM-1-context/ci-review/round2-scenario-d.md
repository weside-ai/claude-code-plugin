# SIM-1 · ci-review · Round 2 · Scenario D (unattended run until merge)

Table-top simulation. Nothing was executed. Skill under test:
`we/skills/ci-review/SKILL.md` (285 lines, was 335). Authoring contract:
`.claude/rules/plugin-authoring.md`. Repo context: `the host repo`,
the host repo's CI rules file, `.weside/config.json`
(`review.available = ["codex","claude","coderabbit"]`).

User request, verbatim: *"automerge ist aktiviert, mach /ci-review bis der PR
gemerged ist, maximal 3 Runden. Ich bin weg."* — then absent for an hour.

World: branch `fix/TICKET-000-copy-fix`, PR #3730, base `main`, `gh` authed,
auto-merge (squash) armed.

---

## Trace

### Round 0 — reading the revised skill against the request

Round 1 hit two hard forks before the first tool call. Both are gone.

Fork 1, the single-pass default. Line 54–58 now reads:

> **One pass by default.** … Re-enter Phase 4 only with a concrete reason (…) — **or because the user set a budget** ("bis gemerged, max 3 Runden"): an explicit user instruction outranks the default and sets the cap. (54–58)

The permission list is no longer closed over PR properties. I enter Phase 4 on
the user's instruction, on the skill's own authority. No improvisation.

Fork 2, the cap and the undefined unit. Line 257–260:

> One **cycle** = one push plus the checks and re-reviews it triggers. … Loop when a single-pass exception applies, or up to the cap the user set — a user-stated budget ("max 3 Runden") replaces the default cap of 2. (257–260)

The unit is defined once, and the definition is decisive here. Arithmetic,
carried explicitly because it is the proof the headline fix landed:

| | push | the checks it triggers | cycle |
|---|---|---|---|
| Round 1 | push #1 | round-2 checks (`claude-review` red) | cycle 1 |
| Round 2 | push #2 | round-3 checks (all green) | cycle 2 |
| Round 3 | — | observation only, tail of cycle 2 | — |

Terminal state 1 fires **inside cycle 2**. Even the default cap of 2 suffices;
the user's 3 never binds. In round 1 the two candidate readings of "cycle"
differed by exactly the decisive round — they no longer do.

I also read the gate before collecting (17–22), which round 1 had to reconstruct
from the host repo's CI rules.

---

### Round 1

**1a — resolve the run's state (74–84).** The variables now ship with the
commands that fill them; nothing invented:

```
Bash: gh auth status >/dev/null 2>&1 && GH_AVAILABLE=true || GH_AVAILABLE=false   → true
Bash: PR=$(gh pr view --json number --jq .number)                                 → 3730
Bash: REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)               → the app repo
      OWNER=the host repo-ai  REPO_NAME=the host repo
Bash: BASE_REF=$(gh pr view 3730 --json baseRefName --jq .baseRefName)            → main
Bash: gh pr view 3730 --json mergeable,mergeStateStatus,autoMergeRequest
      → mergeable=MERGEABLE, mergeStateStatus=BLOCKED, autoMergeRequest={squash}
```

`mergeable` is not `CONFLICTING`, so the 1a conflict branch (89–91) is inert.
`autoMergeRequest != null` is captured **here**, in round 1, which is what makes
terminal state 1 evaluable later.

**1b — the four sources (98–120).** Run as written:

```
Bash: gh pr checks 3730
  → Backend (Test)   fail   https://github.example/actions/runs/<id>
     CI Summary      fail
     claude-review   pass · codex-review pass · Mobile (Test) pass · (rest pass)

Bash: gh api graphql -f query='…reviewThreads(first:100)…' -F pr=3730 -F owner=the host repo-ai -F repo=the host repo
  → 1 node: coderabbitai[bot], "Nitpick: 'Änderungen gespeichert' vs 'Gespeichert' — pick one voice"

Bash: gh api repos/the app repo/pulls/3730/reviews --jq 'group_by(.user.login)[] | last | …'
  → === coderabbitai[bot] === (summary body, no new findings)

Bash: gh api repos/the app repo/issues/3730/comments --paginate \
      --jq '[.[] | select(.user.type=="Bot" or (.user.login|endswith("[bot]")))
           | select(.body|test("VERDICT:|SEV:|Code Review"))] | group_by(.user.login)[] | last | .body'
  → === claude[bot] === "## Code Review … <!-- VERDICT:PASS -->"   (no SEV rows)
```

Source 4 is now a **shape** filter, not a name filter, and it groups per author.
Round 1's contradiction between line 95 ("Do not special-case a reviewer by
name") and a hardcoded `test("claude";"i")` is gone; a `codex-review` verdict
posted as an issue comment would now be collected, and `github-actions[bot]` is
caught by the login suffix — which the host repo's CI rules line 67–68 says is a real
posting identity for `claude-review`.

**1c — every non-pass check is a BLOCKING row (122–140).** The generic
error→fix table is gone; the instruction is to read the log:

```
Bash: gh run view <run-id> --log-failed
  → tests/mobile/toast.spec.ts:41
    AssertionError: expected 'Gespeichert' to equal 'Änderungen gespeichert'
```

Classified per 134–135 as "a real finding", not the runner. `CI Summary` fail is
the roll-up of the same job — one root cause, no re-run.

**1d — findings table (142–158).**

| # | Source | Bot? | Severity | File:Line | Issue | Thread ID | Action |
|---|---|---|---|---|---|---|---|
| 1 | CI · Backend (Test) | — | BLOCKING | tests/mobile/toast.spec.ts:41 | asserts pre-change copy | — | fix |
| 2 | CodeRabbit | yes | NITPICK | src/mobile/…/toast.ts | voice inconsistency | PRRT_kwDO… | fix (finish-first, 49–52) |

The claude[bot] PASS comment produces zero rows, per 154–156 ("splits into one
row per `SEV:` finding"). Round 1 flagged that the gate-is-green signal leaves no
trace; it still leaves none in the *table*, but 17–22 now defines the gate
separately, so the signal has a home. Not re-raised.

No human threads (158 inert).

**Phase 2 (170–177).** Findings > 0; the stop condition (173–175: every required
check non-red, zero unresolved threads, zero open SEV) fails on check #1.

**3a–3c (185–198).**

```
Edit: tests/mobile/toast.spec.ts   (assertion → 'Änderungen gespeichert')
Edit: src/mobile/…/toast.ts       (unify voice)
Bash: /we:static  → green ;  /we:test (affected: 2 files)  → green
Bash: ls scripts/check-*.sh → run the applicable ones → green
Bash: git add -A && git commit -m "fix: address CI and review findings

TICKET-000" && git log --oneline -1        # HEAD moved
```

`{TICKET}` is gone; 197–198 says "the ticket key in the body when the branch
carries one", and the branch carries `TICKET-000`. No placeholder to resolve.

**3d (200–222).**

```
Bash: REVIEW_ALLOWLIST=$(jq -r '(.review.available // ["greptile","coderabbit","claude"]) | join("|")' .weside/config.json)
      → codex|claude|coderabbit
Bash: gh api graphql … reviewThreads … --jq '… | .id'   → PRRT_kwDO…
Bash: gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=PRRT_kwDO…
```

**3e (224–235).** Re-run with `| length` → 0. Checklist walked:

- [x] every BLOCKING/WARNING row Fixed → rows 1 and 2 fixed
- [x] no skipped BLOCKING → no PR comment owed
- [x] 0 unresolved bot threads
- [x] no human threads

229–231 explicitly warns that the gate covers threads only and points me at the
Action column — the round-1 blindness is patched by checklist rather than by a
fourth precondition, and it holds.

**3f.** No migration. Skip. **3g (245–252).** (a) every check concluded, (b)
checklist clear, (c) n/a → `git push`.

**Round 1 is not a terminal state.** The budget is set (54–58), so I enter
Phase 4. No override invented.

---

### Round 2 (cycle 1's tail, then push #2)

**Phase 4, per cycle (262).**

```
Bash (background): gh pr checks 3730 --watch
  → all conclude; claude-review = fail
```

The wait mechanism is named now (`--watch`); round 1 invented it.

Re-collect all four sources. Threads: none new. Source 4:

```
  → === claude[bot] ===
     "## Code Review
      <!-- SEV:WARNING --> the test now asserts the copy twice …
      <!-- VERDICT:WARNING -->"
```

Two decisions here.

*Is this "the same finding twice" (263–264)?* Line 263 says each cycle must fix
MORE findings, not the same ones, and that a repeat means stop and escalate.
"Same" is still undefined and this finding sits on the **same `file:line` my
round-1 fix edited**. Under a loose reading I stop at round 2 and the PR never
merges. I took the strict reading (different subject, caused by my own fix, no
thread id in common) and continued. That is a judgement the skill does not make
for me — see New defect A.

*Does the gate see it?* Row added to the table:

| # | Source | Bot? | Severity | File:Line | Issue | Thread ID | Action |
|---|---|---|---|---|---|---|---|
| 3 | claude-review (comment) | yes | WARNING | tests/mobile/toast.spec.ts | copy asserted twice | — | fix |

Severity policy line 32: WARNING → MUST fix. And the check itself is red, which
17–22 makes a gate failure independent of the comment ("the gate is the check's
conclusion, not the comment"). Round 1's defect 4 — 3e printing "all clear" on a
live `VERDICT:WARNING` — cannot recur: the row is BLOCKING/WARNING and 3e's
first checklist item covers it.

**Phase 4 does not name Phase 3.** Line 262 is "re-collect all sources, fix what
is new, push again". I re-entered 3a–3g anyway, because 3g's push precondition
(b) "3e's checklist is clear" reads as a standing invariant on any push. An agent
reading only Phase 4's four lines pushes without 3d/3e. Inert here (no new
threads), same as round 1 — see verdict 14.

```
Edit: tests/mobile/toast.spec.ts   (drop the duplicated assertion)
Bash: /we:test (affected)  → green
Bash: git add -A && git commit -m "fix: address CI and review findings

TICKET-000" && git log --oneline -1
Bash: gh api graphql … reviewThreads … | length   → 0
Bash: git push
```

Cycle count: this is push #2 → cycle 2. Cap (default 2, user-granted 3) not
reached under either number. Round 1's hard stop is gone.

---

### Round 3 (cycle 2's tail)

```
Bash (background): gh pr checks 3730 --watch
  → all pass, claude-review pass, codex-review pass, CI Summary pass
Bash: gh api graphql … reviewThreads …                     → 0 unresolved
Bash: gh api repos/…/issues/3730/comments --paginate …     → "<!-- VERDICT:PASS -->"
Bash: gh pr view 3730 --json mergeable,mergeStateStatus,autoMergeRequest
      → MERGEABLE / CLEAN / {squash}
```

**Terminal state 1 (268–270):**

> **Green** — gate satisfied, nothing unresolved. If auto-merge is armed (`autoMergeRequest != null`) and `mergeStateStatus` is clean, the merge fires without you: say so, do not wait for it. (268–270)

The success exit exists now; round 1 fell off the end of a four-step list whose
only terminal was "ask user". Phase 5 (280–285) reports the terminal state.

**And this is where I go off-script for the only time in three rounds.** The
user's stated goal is *bis der PR gemerged ist*. Line 269 tells me to report
"the merge fires without you" and **not** to wait. The scenario says auto-merge
lands ~90 s later. So the skill has me report on a *predicted* merge. I ran one
confirming poll anyway:

```
Bash: gh pr view 3730 --json state,mergedAt     → state=MERGED, mergedAt=2026-08-27T…
```

Nothing in 285 lines authorises that call — `state` and `mergedAt` appear
nowhere. See New defect B.

**Phase 5 report** — findings table with Actions, three fix lines, push status,
per-check gate status, terminal state 1, 0 unresolved bot threads, no human
threads. I added the merge line.

---

### The five questions, answered directly

**1. Does the user's "max 3 Runden" override work?** Yes, twice over. Line 56–58
lets the instruction enter Phase 4 at all; line 259–260 lets it replace the cap.
Round 1's defects 1 and 2 both fail to reproduce.

**2. What is a cycle?** Defined once, at 257: one push plus the checks and
re-reviews it triggers. Scenario D costs 2 cycles (see the Round 0 table), so the
cap is not even load-bearing. Round 1's two readings differed by the decisive
round; the definition removes the difference.

**3. How do I know the PR is merged, and when may I stop?** I *don't* know —
that is the residue. The skill's stop condition is green gate + armed auto-merge
- clean merge state, and 269 forbids waiting past it. Stopping is well-defined;
confirming the merge is not covered.

**4. Terminal state per round.** Round 1: none — budget set, continue.
Round 2: none — `claude-review` red, WARNING must fix, continue. Round 3:
terminal state 1 (Green). States 2 (cap reached, still red) and 3 (blocked,
nothing to fix) are unreached but both are evaluable here, which round 1's Phase
4 was not.

**5. Does the skill tell me to wait for a human who is gone?** No. Line 275–276:
*"When the user is away, 'ask the user' is not available: take the safest branch,
record the decision and the open question in the report, and stop — never expand
the budget on your own."* One honesty clause: that is a *global* fallback, while
3f's "say so and ask" (243) and 263's "escalate" are *local* instructions whose
fallback sits 15–30 lines later and is not cross-referenced. Both are inert here
(no migration, no repeated finding).

---

## Round 1 verdicts

| # | Round-1 defect | Verdict | Evidence (new line numbers) |
|---|---|---|---|
| 1 | Single-pass default has no user-instruction override | **FIXED** | 56–58: *"or because the user set a budget ("bis gemerged, max 3 Runden"): an explicit user instruction outranks the default and sets the cap."* |
| 2 | Cycle cap undefined, absolute, lands on the winning round | **FIXED** | 257 defines the unit (*"One **cycle** = one push plus the checks and re-reviews it triggers"*) and 259–260 makes the user's budget replace *"the default cap of 2"*; the duplicate Rules-block condition that contradicted it is deleted. |
| 3 | Source 4 special-cases `claude` against line 81 | **FIXED** | 114–119 filters by shape — *"filter by SHAPE, not by name: a bot comment carrying a verdict/severity marker"* — with `select(.user.type=="Bot" or (.user.login\|endswith("[bot]")))`; a `codex-review` comment is now collected. |
| 4 | 3e reports "all clear" while a blocking verdict is live | **FIXED at the push boundary** | 229–231: *"**The gate covers threads only.** An open BLOCKING/WARNING from a summary comment (Thread ID "—") is not visible here — check the findings table's Action column before you call it clear"*, backed by checklist item 232 and 3g precondition (b) at 246. Note where the enforcement moved: 3e's scripted `exit 1` (226–227) is still bound to the thread count alone, so the new coverage is a prose checklist item that **warns** rather than a gate that **prevents** — which is why defect 12 stays partial. |
| 5 | Phase 4 has no success exit | **FIXED** | 266–270: *"**Terminal states** — every run ends in exactly one … 1. **Green** — gate satisfied, nothing unresolved."* |
| 6 | `{TICKET}` unresolved placeholder | **FIXED** | 197–198 replaces the placeholder with prose naming its source: *"the ticket key in the body when the branch carries one"*. |
| 7 | Nothing about merge, auto-merge, terminal state | **PARTIALLY FIXED** | 83 collects `mergeable,mergeStateStatus,autoMergeRequest` and 268–270 reads them — but `state`/`mergedAt` appear nowhere and 269 says *"do not wait for it"*, so a run whose goal is "merged" still cannot observe it (New defect B). |
| 8 | "The CI gate" names two things, never defined | **FIXED** | New section 17–22: *"The gate is satisfied when **every required check has concluded non-red** and **zero bot review threads are unresolved**."* One residue is a naming collision, not the old ambiguity (New defect D). |
| 9 | Rules block retells the steps | **FIXED** | The `## Rules` section is gone; the file ends at Phase 5 (285). |
| 10 | `--ci-only` exists only in the Rules block | **FIXED** | 24–25 gives it a body implementation: *"collect sources 1 and 4 only, skip thread collection and the 3d/3e thread steps, still fix and push."* |
| 11 | Frontmatter triggers do not map to distinct branches | **STILL OPEN** | 6–7 still quotes four triggers (`"/we:ci-review", "fix ci", "fix reviews", "ci failed"`); "fix ci" and "ci failed" are synonyms for the one `--ci-only` branch, and the description still opens on the noun phrase *"CI/Review checker and fixer"* rather than a verb. MINOR, unchanged. |
| 12 | No checkable completion criteria anywhere | **PARTIALLY FIXED** | One checklist now exists (232–235, four `- [ ]` items in 3e); Phases 1, 2, 4 and 5 still end in prose. The gain is real — 232 is what closes defect 4 — but it is also the whole of that closure, since the `exit 1` beside it counts threads only. |
| 13 | Unpaired negation at old line 218 | **FIXED** | The line is gone; 154–156 states the positive form (*"a comment cannot be resolved, so it is outside the 3e gate. It is cleared by the re-review after the push…"*). Spot-check of the surviving negations (22, 95, 138, 182, 226) finds all paired. |
| 14 | Phase 4 step 3 prescribes the jump line 176 forbids | **PARTIALLY FIXED** | 262 is still shorthand — *"re-collect all sources, fix what is new, push again"* — and never names 3d/3e; but 245–247 now states the push precondition as a standing invariant (*"Push only when: (a) … (b) 3e's checklist is clear"*), which an agent re-reading Phase 3 will honour. Downgraded BLOCKING → MAJOR. |
| 15 | Reviewer allowlist default defined twice | **FIXED** | The literal appears once, at 207; 150 cites it (*"matches `$REVIEW_ALLOWLIST` (see 3d)"*) and 226 reuses it (*"reusing `$REVIEW_ALLOWLIST` — do not redefine it"*). |
| 16 | No-op prose in 3a and 3b | **FIXED** | 3a is now one steering line (187: *"Accumulate ALL changes — do not commit between fixes"*) and 3b delegates the procedure (190–193: *"`/we:static`, `/we:test` own the procedure"*), keeping only the base-ref and ~50-file clauses. |
| 17 | "Same finding" undefined, escalation has no recipient | **PARTIALLY FIXED** | The recipient half is answered globally at 275–276 (*"take the safest branch, record the decision and the open question in the report, and stop"*); "same" is still undefined at 263–264 and is now the run's top live risk (New defect A). |

Fourteen of seventeen fixed or materially improved, including all five that broke
scenario D. The revision is a real one, not a re-shuffle.

---

## New defects

### A. "The same finding twice" is still undefined, and it is now the only rule that can end the run short of merge — MAJOR

> **Each cycle must fix MORE findings, not the same ones** — the same finding twice means the fix is not landing where the reviewer looks: stop and escalate. (263–264)

Fixing the five blocking defects promoted this line from round 1's MINOR to
load-bearing: it is now the **only** rule in the file that can end scenario D
short of merge.

"Same" is undefined — same thread id? same `file:line`? same subject? — and
round 2's `SEV:WARNING` lands on the very `file:line` my round-1 fix edited. A
loose reader stops at round 2 with the PR unmerged and the user gone: the exact
round-1 failure, re-entered through a different door. I took the strict reading
to keep going, which is a judgement the skill should be making for me.
(The imperative "MORE findings" also invites a cardinality check — round 1 fixes
two, round 2 one, round 3 zero — that the em-dash gloss then contradicts by
talking about identity; the gloss wins, so this is wording, not a second defect.)

**Smallest fix:** rewrite 263 as *"No finding may recur: the same thread id, or
the same `file:line` + severity, appearing in two cycles means the fix is not
landing where the reviewer looks — stop and report terminal state 3. A shrinking
finding count is the normal shape of a converging run."*

### B. Terminal state 1 forbids the one check the user's instruction asks for — MAJOR

> If auto-merge is armed (`autoMergeRequest != null`) and `mergeStateStatus` is clean, the merge fires without you: say so, **do not wait for it**. (268–270)

This is not merely an omission — it is the round-1 defect-1 error class,
reintroduced one section later. Line 56–58 establishes that *"an explicit user
instruction outranks the default"*; 269 then hard-codes a default ("do not wait")
with no user-override clause, against a user whose stated terminal condition is
literally `mergedAt != null`. `state` and `mergedAt` appear nowhere in 285 lines,
so the skill can report a *predicted* merge and nothing else. The scenario merges
90 s after the last check — the cheapest possible confirmation.

**Smallest fix:** append to 270 — *"If the user asked for a terminal state
(\"bis gemerged\"), confirm it once after the last check concludes:
`gh pr view $PR --json state,mergedAt`. Report `MERGED` with its timestamp, or
the blocking `mergeStateStatus`; do not poll beyond one confirmation."*

### C. `gh pr checks` cannot tell you which checks are required — MINOR (inert here)

> The gate is the set of checks the PR's branch protection requires — **read it from `gh pr checks $PR`**, never from memory. (19–20)

`gh pr checks` lists every check run on the head SHA with its conclusion; it
carries no required/optional column. The prescribed instrument cannot answer the
question the sentence asks it. The intent ("don't hardcode the list") is right —
the host repo's CI rules line 9 names `CI Summary`, `claude-review`, `codex-review`, and
that list does drift. Inert in scenario D because every red check *is* required
and the skill fixes everything anyway; it bites when a non-required check is
permanently red and the agent treats it as gate-blocking, i.e. never terminates.

**Smallest fix:** *"read the conclusions from `gh pr checks $PR` and the required
set from `gh pr view $PR --json statusCheckRollup,mergeStateStatus` — a
`mergeStateStatus` of `BLOCKED` with every check green means a required check has
not reported at all."*

### D. "The gate" names two different conditions, 150 lines apart — MINOR

> The gate is satisfied when **every required check has concluded non-red** and **zero bot review threads are unresolved**. (20–22)
> **All green → STOP** only when all three hold: every required check concluded non-red, zero unresolved threads, **zero open SEV findings**. (173–175)

Two conditions vs three. Both are individually correct about *different* things —
20–22 describes what GitHub blocks the merge on, 173–175 describes when *I* may
stop — and the difference is real (a green check with a live SEV comment would
merge but should not be called done). The defect is one word, "gate", for two
referents, which is precisely the collision `plugin-authoring.md` line 40–42
forbids and precisely what round-1 defect 8 was about.

The same word also strands `--ci-only`: 24–25 skips thread collection, while
20–22's gate requires zero unresolved threads, so under that flag the gate is by
construction unevaluable.

**Smallest fix:** name 173–175 *"the stop condition"* and add a half-sentence:
*"the stop condition is the gate plus zero open SEV findings; under `--ci-only`
the thread clause drops from both."*

### E. The default is stated as both 1 and 2 in three lines — MINOR

> **One pass by default.** (54) · Default: stop after the first push and report. (258) · a user-stated budget … replaces the default cap of 2. (260)

Reconcilable (no loop by default; cap 2 once a single-pass exception applies),
but the reader meets "default" twice with different numbers while deciding how
many rounds they may run. Changes no branch in scenario D — the user set the
budget. **Smallest fix:** at 260 write *"replaces both the default (no loop) and
the exception cap of 2."*

### F. `$REVIEW_ALLOWLIST` is used in Phase 1 and defined in Phase 3 — MINOR

Line 150 makes the findings table's `Bot?` column depend on `$REVIEW_ALLOWLIST`
*"(see 3d)"*, but the variable is first assigned at 207, two phases later. In a
fresh shell per Bash call (76) that forward reference is a real ordering hazard.
**Smallest fix:** move the `jq` assignment into the 1a block at 78–83 and let 207
cite it.

Not raised: the `greptile|coderabbit|claude` fallback at 207 still omits `codex`,
but this repo's `.weside/config.json` supplies `codex|claude|coderabbit`, so the
fallback never fires here.

---

## What I needed and did not find

Strictly mechanics Opus 5 would **not** invent unprompted. The list is down from
five to two.

1. **Which checks constitute the gate, and how to read that set.** Not
   inventable: it is repo policy (the host repo's CI rules line 9, plus "an absent check
   is not a passing check"), it drifts, and the skill's prescribed instrument
   cannot report it (New defect C). An agent that guesses either over-blocks on
   an optional red check or under-blocks on a required check that never reported.
2. **What "same finding" counts as.** The skill's own unit, its own stop rule,
   and the two plausible readings differ by whether scenario D reaches merge at
   all (New defect A). A fresh agent cannot derive the intended meaning from the
   text.

Explicitly **not** listed, because I would do them unprompted and did:
`gh pr view --json state,mergedAt` to confirm the merge (New defect B is that the
skill *forbids* it, not that it omits it); `gh run view --log-failed`;
`--watch` to wait for checks; re-entering 3d/3e in cycle 2; resolving a one-word
nitpick on the seam I touched; running only affected tests; batching fixes into
one commit; inferring `TICKET-000` from the branch name.

Round 1 listed merge state, the absent-user fallback, cycle semantics and the
verdict-gates-the-push rule here. Three of those four are now in the file.

---

## What could still be cut

285 lines carries far less dead weight than 335 — the two biggest round-1 targets
(the 1c fix table, the Rules block) are gone, and no section is now pure
paraphrase. What remains:

- **Lines 22, 123–124 and 176** — one invariant stated three times: *"A red
  required check that posted no finding is still red"* (22), *"A red or errored
  required check is a finding even when no bot commented on it"* (123–124), *"A
  red check with an empty findings table is 1c's case, not this one"* (176). Per
  `plugin-authoring.md` line 26–29 this is exactly the drift-start pattern that
  produced round 1's own 307/334 contradiction. Keep 123–124 as the owner; 22 and
  176 become half-clause citations. **~3 lines.**
- **Lines 13 and 15** — *"Collects findings from CI + reviews, fixes them, and
  pushes once everything is addressed"* and *"Core principle: Fix everything.
  Push once. No leftovers."* are the same sentence twice, and both restate the
  frontmatter description. Keep 15. **~2 lines.**
- **Lines 62–68 (the workflow code block)** — a five-step map whose steps are the
  phase headings verbatim, and whose step 3 repeats the Phase 3 header at 180
  (`Fix → Validate → Commit → Resolve → Push`). Useful as orientation, but it is
  the third statement of the phase order. **~7 lines**, cut or reduce to two.
- **Lines 49–52 (finish-first)** — a near-verbatim restatement of `the host repo`'s
  always-loaded `workflows/finish-first.md`. Legitimate in a plugin skill (it
  cannot cite a host repo's rule), so this is a *note*, not a cut: it is the one
  place the file duplicates something with an owner elsewhere.

Explicitly **not** cuttable: lines 40–42's good/bad skip pair looks like
redundancy but is **required** by `plugin-authoring.md` line 74–76 ("Quality
judgments come as good/bad pairs"); line 76–77's fresh-shell warning is
harness-specific and real; line 154–156's Thread-ID-"—" aside is what closes
round-1 defect 4.

Net: roughly 12 of 285 lines are duplication, against ~35 of 335 in round 1 — and
the surviving duplication is one invariant, not a whole section. The file has
room for New defect A's rewrite and New defect B's one-line confirmation poll
without growing.

---

## Grade

**4 / 5** — a fresh Opus agent now runs scenario D end to end on the skill's own
authority: the user's budget legitimately overrides the default, "cycle" is
defined and the arithmetic lands inside the cap, the verdict comment is collected
by shape and gated by the 3e checklist, terminal state 1 exists, and 275–276
answers "the human is gone" without ever telling me to wait for one; it misses 5
because the one rule that can still end the run short of merge ("the same finding
twice") is undefined, and terminal state 1 forbids the 90-second
`gh pr view --json state,mergedAt` that answers the only question the user
actually left the room to get.
