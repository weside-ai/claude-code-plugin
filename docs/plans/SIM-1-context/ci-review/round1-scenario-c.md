# SIM-1 · ci-review · Round 1 · Scenario C

**Table-top simulation.** Nothing was executed. Role: main agent in `the host repo`, user typed
`/we:ci-review`, branch `feat/TICKET-000-escalation`, PR #3725, base
`feat/TICKET-000-integration`, 9 files (Python + TypeScript), one factually-wrong BLOCKING finding.

Skill under test: `we/skills/ci-review/SKILL.md` (335 lines).

---

## Trace

### Step 0 — skill loads, no argument parsing

The user said `/we:ci-review` with no flag. The only flag the skill knows is on line 335
(`- **`--ci-only`flag** — skip reviews, only check CI status.`), in the Rules block, with no
statement of where arguments arrive or what the default is. I take the default path by
inference, not by instruction.

### Step 1 — Phase 1 preamble (L68–71): resolve five variables, no commands given

> L68–71: `Resolve, and keep for the rest of this run: **`$GH_AVAILABLE`** … **`$PR`** …
> **`$BASE_REF`** … and **`$REPO` / `$OWNER` / `$REPO_NAME`** for the GraphQL calls below.
> The later blocks all guard on`$GH_AVAILABLE` and `$PR`.`

The skill names the variables and gives **zero** commands to derive them, then uses them as live
shell variables in four subsequent code blocks (L84–116, L226–243, L251–266, L282). In Claude
Code every Bash call is a **fresh shell** — nothing set in one call survives into the next.

Followed literally, my first tool call is the L83–117 block verbatim:

```bash
if [ "$GH_AVAILABLE" = true ] && [ -n "$PR" ]; then
  gh pr checks $PR
  …
else
  echo "INFO: gh unavailable or no PR found — skipping remote CI/review collection. Local quality gates are authoritative."
fi
```

`$GH_AVAILABLE` and `$PR` are unset → the guard is false → **the entire remote collection is
skipped silently and the skill's own text (L72–74) tells me to declare local gates
authoritative and "say so once rather than failing."** In scenario C `gh` is authenticated and
PR #3725 exists. The skill's happy path terminates the run in its first tool call with a
false statement to the user. **This is defect 1.**

Going there and then correcting (as any competent agent would, unprompted), I issue what the
skill did not:

```bash
gh auth status                                          # → authenticated  → GH_AVAILABLE=true
gh pr view --json number,baseRefName,headRefName -q .    # → 3725, feat/TICKET-000-integration
gh repo view --json owner,name -q '.owner.login+"/"+.name'   # → the app repo
```

`$BASE_REF` = `feat/TICKET-000-integration` — **not main**. The skill is right to insist on this
(L69–70, L191) and right that nothing later depends on it in scenario C (no migration → 3e-bis
does not fire; 3b's affected-test mapping does).

### Step 2 — 1a source (1): CI status

```bash
gh pr checks 3725
```
→ all `pass` except `claude-review` = `fail`. Note: `gh pr checks` **exits non-zero** when any
check fails; the skill never says so, and it is the first command inside a compound block.

The skill now forks me with no rule: is `claude-review: fail` a **CI failure** (Phase 1c,
"Pre-existing CI failures … are YOUR problem", with a fix table of ImportError/flaky/coverage/lint
— none of which apply) or is it the **same finding** as the summary comment collected in source
(4)? The skill never states the check↔comment identity. **Defect 5.** I decide, unaided, that
it is the latter and do not open a separate CI row.

### Step 3 — 1a source (2): unresolved review threads (PRIMARY)

```bash
gh api graphql -f query='query($pr:Int!,$owner:String!,$repo:String!){ repository(owner:$owner,name:$repo){ pullRequest(number:$pr){reviewThreads(first:100){nodes{ id isResolved isOutdated comments(first:1){nodes{author{login} body path line}} }}}}}' \
  -F pr=3725 -F owner=the host repo-ai -F repo=the host repo \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false)'
```

Returns the five threads. `author.login` classification per L151–153:

| # | login | bot? | path:line | text |
|---|---|---|---|---|
| T1 | `coderabbitai[bot]` | yes | `apps/backend/app/services/service.py:88` | 🛠️ Refactor suggestion: extract the retry loop |
| T2 | `coderabbitai[bot]` | yes | `apps/mobile/src/hooks/useThing.ts:41` | ⚠️ Potential issue: missing dep in useEffect |
| T3 | `coderabbitai[bot]` | yes | `apps/backend/tests/test_service.py:12` | 🧹 Nitpick: unused import |
| T4 | `github-actions[bot]` | yes | `apps/backend/app/services/service.py:120` | Claude inline review thread |
| T5 | `maintainer` | **no** | `apps/backend/app/services/service.py:60` | "das war Absicht, siehe ADR" |

### Step 4 — 1a source (3): latest review body per bot

```bash
gh api repos/the app repo/pulls/3725/reviews \
  --jq 'group_by(.user.login)[] | last | select(.user.login | endswith("[bot]")) | "=== \(.user.login) ===\n\(.body)"'
```
→ CodeRabbit walkthrough body (context only, per L98).

### Step 5 — 1a source (4): the Claude summary issue comment

```bash
gh api repos/the app repo/issues/3725/comments --paginate \
  --jq '[.[] | select(.user.login|test("claude";"i")) | select(.body|test("## Code Review"))] | sort_by(.created_at) | last | .body // "(no Claude review comment)"'
```
→ correctly returns the **newest** of the three. Three SEV rows + `<!-- VERDICT:BLOCKING -->`.

⚠️ The filter is `.user.login|test("claude";"i")` (L112). the host repo's CI rules file states: *"the action posts as `claude[bot]` **or** `github-actions[bot]`; anything
grepping only one login misreads it."* Thread T4 in this very PR is a Claude review thread authored
by `github-actions[bot]` — direct evidence the other login is live in this repo. Under that login
this jq returns `"(no Claude review comment)"` and the run proceeds believing there is no Claude
review while `claude-review` is red. **Defect 2.**

### Step 6 — 1d findings table

The skill gives no dedupe rule between sources (2) and (4). T4 (`service.py:120`,
github-actions[bot], a Claude inline thread) and the SEV rows come from the same reviewer run and
plausibly restate one finding — one of them is auto-resolvable, the other is not (L158–161). I
build the table with both and no instruction on which to act on. **Defect 6.**

| # | Source | Bot? | Sev | File:Line | Issue | Thread ID | Action |
|---|---|---|---|---|---|---|---|
| 1 | Claude | — | **BLOCKING** | service.py (~118) | target_ref written without tenant filter | — | ? |
| 2 | Claude | — | **WARNING** | service.py | new preset row has no escalation target | — | fix |
| 3 | Claude | — | SUGGESTION | service.py | rename `p` → `preset` | — | fix (cheap) |
| 4 | Claude(inline) | yes | ? | service.py:120 | T4 body | `PRRT_4` | ? dup of 1 |
| 5 | CodeRabbit | yes | SUGGESTION | service.py:88 | extract retry loop | `PRRT_1` | skip+reason |
| 6 | CodeRabbit | yes | **WARNING** | useThing.ts:41 | missing useEffect dep | `PRRT_2` | fix |
| 7 | CodeRabbit | yes | NITPICK | test_service.py:12 | unused import | `PRRT_3` | fix (trivial) |
| 8 | human | no | — | service.py:60 | "das war Absicht, siehe ADR" | `PRRT_5` | needs user confirm |

Severity for rows 4–7 is read from the **text** per L154–156 (⚠️ Potential issue → Minor →
WARNING → must fix; 🧹 Nitpick → may skip; 🛠️ Refactor suggestion → may skip).

### Step 7 — the factually-wrong BLOCKING finding (row 1)

I read `apps/backend/app/services/service.py` around the write and find the call site
three lines up already runs `await apply_tenant_scope(db, uid)`, so the transaction is
tenant-scoped and the finding is wrong.

What the skill authorises:

> L21: `**MUST fix.** Only exception: the reviewer is demonstrably factually wrong (cite evidence).`
> L33–34: `a finding may be skipped ONLY when: the reviewer is **factually incorrect** (cite evidence)`

What the skill does **not** say, anywhere in 335 lines:

- what "cite evidence" means as an artifact — file:line? a test name? a quoted rule?
- **where the dispute is recorded.** There is no instruction to reply on the PR, to post a
  comment, to edit the PR body, or to re-request review. The only destination the skill offers is
  Phase 5 (L313–320): `Skipped items with factual justification` — a **terminal report to the
  user**. The PR, the reviewer, and the required status check never see it.
- no good/bad pair showing what a sufficient dispute looks like versus an insufficient one.

So my dispute lives in my own chat output. **Defect 3 (BLOCKING).**

### Step 8 — and the gate never goes green

> L158–161: `Its **Thread ID is "—"** (a comment can't be resolved) and it is **not** subject to
> the 3e thread gate — it is confirmed by the re-review after push (3d note / Phase 4): the next
> run posts a delta with ✅ Fixed and a`VERDICT:PASS`, which is what the CI gate checks.`
> L217–220: `after you push the fixes, the Claude review re-runs and posts a delta with ✅ Fixed
> and`VERDICT:PASS`; … so a green gate after push is the proof.`

Both sentences assume every Claude finding was **fixed**. Row 1 is *skipped as factually wrong* —
the code for it is unchanged, so the re-review sees the identical code and posts
`<!-- SEV:BLOCKING -->` and `<!-- VERDICT:BLOCKING -->` again. `claude-review` is a **required**
check in this repo (the host repo's CI rules: *"Required status checks: `CI Summary`, `claude-review`,
`codex-review`"*), so PR #3725 is unmergeable, permanently, and the skill's own "proof of done"
(a green gate) can never be produced. The skill contains no fallback: no "post the dispute as a
PR comment so the next run can see it", no "tell the user the gate needs a human override", no
"escalate". Defect 3 continued — **this is the scenario's central failure.**

### Step 9 — human thread T5, read too late

L152–153 / L213 / L330 say: mark "needs user confirm", never auto-resolve, surface it to the
user. The only place the skill surfaces it is Phase 5 — **after** the fix commit and **after**
the push (L280–289, L313–320). T5 sits on `service.py:60`, the same file and adjacent
region as rows 1–4, and says "that was deliberate, see the ADR". Following the skill in order I
fix rows 2/3/6/7 and push before the user ever sees the objection that may cover the code I
touched. There is no step "read human threads before fixing overlapping bot findings" and no
gate holding the push on an unanswered human objection (L270 explicitly exempts them).
**Defect 4.**

### Step 10 — Phase 2 Triage

L165 (`0 findings → STOP`) does not fire. L167–170 re-states the L19–23 table. No new decision.

### Step 11 — Phase 3a/3b/3c

3a (L178–181) is one line I would do unprompted. 3b: stacks touched = Python + TypeScript, 9
files (< 50, no test-config change → affected-only, base ref `feat/TICKET-000-integration`):

```bash
ruff check --fix apps/backend/app/services/service.py apps/backend/tests/test_service.py
ruff format apps/backend/app/services/service.py apps/backend/tests/test_service.py
mypy apps/backend/app/services/service.py
a test apps/backend/tests/test_service.py
yarn workspace @the host repo-ai/mobile lint --fix src/hooks/useThing.ts
yarn workspace @the host repo-ai/mobile tsc --noEmit
yarn jest --findRelatedTests apps/mobile/src/hooks/useThing.ts
ls scripts/check-*.sh   # then run the ones that exist
```

3c (L199–206):

```bash
git add apps/backend/app/services/service.py apps/mobile/src/hooks/useThing.ts apps/backend/tests/test_service.py
git commit -m "fix: address CI and review findings

{TICKET}"
```

`{TICKET}` (L205) is an undefined placeholder — never introduced, never derived. I must guess
`TICKET-000` from the branch name. **Defect 9.**

### Step 12 — 3d resolve bot threads

```bash
REVIEW_ALLOWLIST=$(jq -r '(.review.available // ["greptile","coderabbit","claude"]) | join("|")' .weside/config.json 2>/dev/null || echo "greptile|coderabbit|claude")
```
the host repo has no `.weside/config.json` → jq exits 2 → fallback fires → `greptile|coderabbit|claude`.
This one works. But it is a **fresh shell again**: `$GH_AVAILABLE`, `$PR`, `$OWNER`, `$REPO_NAME`
in the very next `if` on L228 are empty once more, so the literal block resolves **nothing** and
prints nothing (Defect 1 recurs, silently — there is no else branch here at all).

With substituted literals, T1–T4 are selected (all `[bot]`), T5 (`maintainer`) correctly excluded,
and four `resolveReviewThread` mutations fire — **including T1 and T3, which I skipped or
trivially handled.** The skill never says to post a reply stating the skip reason before
resolving, so CodeRabbit's refactor suggestion is closed with no visible rationale on the PR;
the "short explicit reason" (L23) exists only in my terminal report. **Defect 7.**

Also: 3d runs **before** the push (L208, L280), so the reviewer's threads are marked resolved
against code that does not yet exist on the remote.

### Step 13 — 3e hard gate

Re-query → 0 unresolved bot threads → `All bot threads resolved.` T5 does not block (L270).

### Step 14 — 3e-bis

No Alembic migration in the diff → skipped. (Latent contradiction recorded as Defect 8: 3e-bis
mandates a rebase, 3f mandates a bare `git push`, which cannot succeed after a rebase, and
the host repo's `.claude/rules/workflows/git-workflow.md` requires explicit user instruction before
force-pushing.)

### Step 15 — 3f push

L282: push only after `gh pr checks` shows no `pending`/`in_progress`. Everything already
concluded (`claude-review` = fail), so the gate is satisfied by a **failed** check — the skill's
wording only excludes pending states, never "no failing check remains". `git push`.

### Step 16 — Phase 4

L293–298: opt-in only. Is "a fix you are genuinely unsure resolved the finding" met? My row-1
decision was a *skip*, not a fix — the literal exception list does not name "I disputed a
BLOCKING finding and want to see whether the gate accepts it". "high-stakes PR
(security-sensitive…)" arguably applies since the disputed finding is a claimed tenant-scope
leak. The skill leaves this to judgement. Entering the loop anyway:

```bash
gh pr checks 3725   # after ~4 min
```
→ `claude-review` **fail** again, same `SEV:BLOCKING`, same `VERDICT:BLOCKING`. L309: *"If the
same finding appears 2 times, you have a structural problem — stop and escalate."* That is the
only exit, and it is buried in an opt-in phase the default (L45–52) tells me not to enter.

**Answer to the scenario's question: the gate never goes green.** The dispute is recorded
nowhere the gate can read, and the skill's completion model has no state for
"correctly-disputed BLOCKING".

### Step 17 — Phase 5 report

Findings table, fix list, the row-1 justification, push status, `claude-review` = fail,
0 unresolved bot threads, T5 surfaced to the user for the first time.

---

## Conformance checklist

- [ ] **Phase 1 preamble (L68–71)** — names five variables, gives no commands and no note that
      shell state does not survive between tool calls; the literal path skips all remote work.
- [x] **1a sources (2)(3)** — thread and review-body queries are concrete, complete and correct.
- [ ] **1a source (4)** — jq matches only `claude`, not `github-actions[bot]`, contradicting the
      repo's own documented behaviour; misses the review entirely under the other login.
- [ ] **1b/3f push gate** — "no `pending`/`in_progress`" is satisfied by a *failing* check; no
      wait mechanism given, and the repo forbids bash wait loops.
- [ ] **1c CI failures** — fix table covers none of the actual failure (`claude-review`), and the
      check↔summary-comment identity is never stated.
- [x] **1d table shape** — columns and the bot/severity derivation rules are unambiguous.
- [ ] **1d dedupe** — no rule for the same finding arriving as both an inline thread and a SEV row.
- [x] **Phase 2** — trivially unambiguous (and adds nothing over L19–23).
- [x] **3a/3b/3c mechanics** — affected-only validation, base-ref rule, one commit: clear.
- [ ] **3c commit body** — `{TICKET}` is an undefined placeholder.
- [ ] **3d** — resolves skipped bot threads with no reply recording the reason; runs pre-push.
- [x] **3e** — a real, checkable hard gate; the one genuinely well-built step.
- [ ] **3e-bis vs 3f** — rebase then bare `git push` cannot both hold.
- [ ] **Skip/dispute path** — authorised (L21, L33) but has no artifact, no format, no
      destination, and no terminal state when the disputed finding is a required gate's verdict.
- [ ] **Human threads** — "surface to the user" is only honoured in Phase 5, after the push.
- [ ] **Phase 4 entry** — the exception list does not cover a disputed BLOCKING; judgement call.
- [ ] **No phase ends in `- [ ]` completion criteria** (plugin-authoring L71–73).

---

## Skill defects

### 1. The five run-scoped variables are never derived, and every code block is a fresh shell — BLOCKING

> L68–71: `Resolve, and keep for the rest of this run: **`$GH_AVAILABLE`** … **`$PR`** …
> **`$BASE_REF`** … and **`$REPO` / `$OWNER` / `$REPO_NAME`** … The later blocks all guard on
> `$GH_AVAILABLE` and `$PR`.`
> L84: `if [ "$GH_AVAILABLE" = true ] && [ -n "$PR" ]; then`
> L115: `echo "INFO: gh unavailable or no PR found — skipping remote CI/review collection. Local quality gates are authoritative."`

In scenario C `gh` is authenticated and PR #3725 exists, yet the first block as written takes the
else branch (unset vars) and instructs me to declare local gates authoritative — a silent,
*self-confirming* full skip of CI and every review source, with a false message to the user. The
3d block (L228) has no else branch at all, so it fails invisibly. **Fix (smallest):** replace L68–71
with the three derivation commands and one sentence — "each Bash call is a fresh shell: substitute
the resolved literals into every command below, do not rely on exported variables."

### 2. The Claude-comment filter greps one login, and this repo uses two — BLOCKING

> L112: `--jq '[.[] | select(.user.login|test("claude";"i")) | select(.body|test("## Code Review"))]`

the host repo's CI rules file: *"Red `claude-review` WITH a PASS comment is
the gate, not the review — the action posts as `claude[bot]` or `github-actions[bot]`; anything
grepping only one login misreads it."* Thread T4 in this PR is a Claude thread authored by
`github-actions[bot]`. Under that login the jq yields `"(no Claude review comment)"`, the run
reports "no Claude findings" while `claude-review` is red, and rows 1–3 never enter the table.
**Fix:** `select(.user.login|test("claude|github-actions";"i"))`.

### 3. A correctly-disputed BLOCKING finding has no destination and no terminal state — BLOCKING

> L21: `Only exception: the reviewer is demonstrably factually wrong (cite evidence).`
> L33–34: `a finding may be skipped ONLY when: the reviewer is **factually incorrect** (cite evidence)`
> L160–161: `it is confirmed by the re-review after push …: the next run posts a delta with ✅ Fixed
> and a`VERDICT:PASS`, which is what the CI gate checks.`
> L219–220: `so a green gate after push is the proof.`
> L317: `- Skipped items with factual justification`

The skill authorises exactly the move scenario C requires, then routes its output to a terminal
report the PR cannot see. L160/L219 assume every Claude finding was fixed; a skipped one leaves
the code identical, the re-review re-posts `VERDICT:BLOCKING`, and a required check stays red
forever. The skill never says: post the dispute as a PR comment / reply so the next reviewer run
and the human can read it; never defines what "cite evidence" produces; never states that a
skipped Claude BLOCKING means the PR needs a human gate override, and never tells the user so.
**Fix:** two sentences in 3d — "A skipped or disputed Claude finding is posted as a PR comment
(`gh pr comment $PR --body …`) quoting file:line evidence *before* the push; a Claude BLOCKING
skipped this way keeps `claude-review` red — Phase 5 must state that the PR needs a human
override and name the evidence."

### 4. Human threads are surfaced only in Phase 5, i.e. after the fixes and after the push — MAJOR

> L31: `Human-authored threads are never auto-resolved — surface them to the user.`
> L152–153: `Human threads → mark "needs user confirm", never auto-close.`
> L270: `Human-authored threads do not block this gate — list them in the report instead.`

T5 (`maintainer`, `service.py:60`: "das war Absicht, siehe ADR") is an explicit human veto on
the same file and neighbourhood as rows 1–4. Following the phase order I fix, commit, resolve and
push before the user is shown it. "Surface to the user" is not a step anywhere before Phase 5.
**Fix:** one line in Phase 2 — "Read every human thread before fixing; where a human thread
overlaps a bot finding's file region, ask the user before changing that code."

### 5. `claude-review: fail` fits neither 1c's CI table nor a clean identity with source (4) — MAJOR

> L130–132: `**Pre-existing CI failures that block your PR are YOUR problem.** … Common fixes:`
> (table rows: ImportError · Flaky test · Coverage · Lint/type error)

The single failing check in this scenario is a *review* gate whose content lives in an issue
comment. None of the four table rows applies, and the skill never states that a red review check
must not be triaged as an independent CI finding. **Fix:** one row in the table — "review gate
(`claude-review`/`codex-review`) red → not a separate finding; its content is source (4), fix
those SEV rows."

### 6. No dedupe rule between an inline review thread and the summary comment — MAJOR

> L88–89: `PRIMARY — the resolvable unit: ALL unresolved review threads, ANY author.`
> L157–159: `**Claude Code Review** (source 4) is a summary comment, not threads: split it into one
> row per`<!-- SEV:* -->`finding`

T4 (`github-actions[bot]` on `service.py:120`) and SEV row 1 come from the same reviewer
run and may be one finding wearing two hats — one auto-resolvable, one not. Resolving T4 while
disputing its twin closes half a finding. **Fix:** one line in 1d — "collapse rows that share
reviewer + file + region into one; keep the thread id, keep the higher severity."

### 7. Bot threads are resolved without any reply recording the fix or the skip reason — MAJOR

> L23: `**may** be consciously skipped — with a short explicit reason in the report.`
> L208–212: `resolve every **bot-authored** unresolved thread you handled — fixed **or**
> consciously skipped-with-reason.`
> L240–242: the resolve loop — a bare `resolveReviewThread` mutation, nothing else.

T1 (refactor suggestion, skipped) and T3 (nitpick) are closed with no trace on the PR; the reason
exists only in my terminal output, which no reviewer or later reader sees. the host repo's CI rules
requires threads be *"resolved as hygiene… fixed or skipped with a reason"* — a reason with no
recipient is not one. **Fix:** in the loop, `gh api …/pulls/$PR/comments/$cid/replies` (or
`gh pr comment`) with one line — "Fixed in <sha>" / "Skipped: <reason>" — before the mutation.

### 8. 3e-bis mandates a rebase, 3f mandates a bare `git push` — MAJOR (latent here)

> L274: `rebase onto`origin/${BASE_REF}`BEFORE the final push`
> L288: `git push`

After a rebase, `git push` is rejected; the fix is `--force-with-lease`, which
the host repo's `.claude/rules/workflows/git-workflow.md` gates on explicit user instruction
(*"Require explicit user instruction before: … force-pushing"*). The skill dead-ends its own
migration path. Not triggered in scenario C (no migration) but structurally broken.
**Fix:** L288 → "`git push` — after a 3e-bis rebase, `--force-with-lease`, and ask the user first."

### 9. `{TICKET}` is an undefined placeholder — MINOR

> L203–205: `git commit -m "fix: address CI and review findings\n\n{TICKET}"`

Never introduced, never derived. I guess `TICKET-000` from the branch. **Fix:** "`{TICKET}` = the key
in the branch name (`<type>/WA-XXX-…`); omit the line if the branch carries none."

### 10. The `--ci-only` flag exists only in the Rules block — MINOR (plugin-authoring violation)

> L335: `- **`--ci-only`flag** — skip reviews, only check CI status.`

plugin-authoring L26–28: *"A `## Rules` section at the end of a skill contains ONLY invariants
that are not already stated in the steps."* This is the inverse failure — a **behaviour**
(a whole alternate execution mode) whose single definition is the Rules block, with no argument
handling anywhere in Phases 1–5. **Fix:** move it to a "## Invocation" line above Phase 1.

### 11. The Rules block paraphrases the steps — MAJOR (plugin-authoring violation)

> plugin-authoring L26–29: `**Rules blocks don't retell steps.** A`## Rules`section at the end of
> a skill contains ONLY invariants that are not already stated in the steps. A Rules block that
> paraphrases the steps is the start of drift: two places, one behavior, and only one gets updated.`

L326 even announces the violation: `The severity policy and Phases 1–5 above are the spec — reminders:`
— then L328–334 restate 3c/3f (L199–206, L280–285), 3d's human-thread rule (L212–213, L270),
source 4's no-thread note (L110, L158–161, L217–220) and Phase 4's cap (L293–309). Four bullets,
zero new invariants. In this scenario the drift already exists: L23 says a skipped SUGGESTION
needs a reason "in the report", L211 says "skipped-with-reason", L330–332 say neither, and none
says where. **Fix:** delete L326–334; keep only L335 (moved per defect 10).

### 12. Single-owner violations inside and across files — MAJOR (plugin-authoring violation)

> plugin-authoring L13–15: `Every rule, procedure, schema, or template is defined in **exactly one
> file** … Every other place cites it with one sentence + path.`

- "never auto-resolve human threads": L31, L152–153, L212–213, L270, L330 — **five** statements.
- "the Claude comment has no thread / is confirmed by the re-review": L110, L158–161, L217–220,
  L331–332 — **four**, and they disagree in strength ("a green gate after push is the proof"
  vs "confirmed by the re-review").
- Severity/skip policy: L19–23, L28, L33–36, L167–170, L317, L326 — **six**.
- **Cross-file:** L38–43 ("Finish-first before ticketizing") is a near-verbatim restatement of
  the host repo's `.claude/rules/workflows/finish-first.md`, which is an always-loaded rule in this
  repo — a second owner in a second repo, already in context when the skill runs.
**Fix:** one owner each; L38–43 → "Finish-first applies (see `workflows/finish-first.md`)."

### 13. No phase ends in checkable completion criteria — MAJOR (plugin-authoring violation)

> plugin-authoring L71–73: `**Completion criteria are checkable.** A phase ends with`- [ ]`items
> the agent can verify (can it tell done from not-done?), not with prose like "when everything
> works". Where it matters, the checklist is exhaustive.`

335 lines, five phases, **zero** `- [ ]` items. 3e is the only step with a mechanical done-check,
and it is a shell gate rather than a checklist. Concretely in scenario C, "Phase 1 is done" has no
test — which is exactly how defect 1's silent skip passes for a completed collection.
**Fix:** a 3–5 item checkbox list closing Phase 1 and Phase 3.

### 14. The one decision that needs a good/bad pair does not get one — MAJOR (plugin-authoring violation)

> plugin-authoring L74–76: `**Quality judgments come as good/bad pairs.** Whenever a skill teaches
> what "good" looks like (a test, a ticket, a brief), show a contrasting pair — never an isolated
> recommendation or an adjective.`

"demonstrably factually wrong (cite evidence)" (L21, L33) is exactly such a judgment and arrives
as an adjective. Scenario C is the hard case: is "the call site three lines up already ran
`apply_tenant_scope`" a demonstration, or do I owe a test name? No pair, no format, no threshold.
**Fix:** two lines under L36 — good: *"BLOCKING 'no tenant filter' → disputed: `service.py:115`
runs `apply_tenant_scope(db, uid)` on the same transaction; pinned by `test_preset_rls_scope`."*
bad: *"I checked, it's fine."*

### 15. Unpaired negations — MINOR (plugin-authoring violation)

> plugin-authoring L65–68: `**Pair every negation.** "Don't X" alone steers by prohibition and
> backfires; write the positive action next to it.`

L218–219: `Don't try to`resolveReviewThread`it (there's nothing to resolve) and don't treat its
absence from the thread list as "missed".` — two bare prohibitions before any positive form; the
positive ("its findings are confirmed by the re-review") is a separate sentence and, per defect 3,
false when the finding was disputed. Also L81 (`Do not special-case any reviewer by name`).
**Fix:** fold into one positive sentence — "Source 4's findings are tracked in the table and
confirmed by the post-push verdict; there is no thread to resolve."

---

## What I needed and did not find

Strictly the mechanics an Opus agent would **not** produce unprompted:

1. **Where a dispute is written back to GitHub, and in what form.** Left alone I would report the
   dispute to the user and stop; posting `gh pr comment` with file:line evidence so the *next*
   reviewer run and the human gate-approver can see it is a repo-protocol choice, not a default.
2. **That a skipped Claude BLOCKING leaves a required check red, and that this must be stated to
   the user as "needs a human override".** The skill actively teaches the opposite (L160, L219).
3. **The `claude[bot]` / `github-actions[bot]` dual login** — repo-specific knowledge; the skill's
   own jq would have misled me had the login differed.
4. **The check↔comment identity** (`claude-review` fail == source-4 content, not a second finding).
5. **Reply-before-resolve** as a required step, and the exact reply text convention.
6. **Whether an open human thread blocks the push.** A defensible protocol decision either way; I
   need the repo's answer, and L270's "does not block" is stated only for the *bot* gate.

Everything else in the trace — deriving `$PR`/`$OWNER`, affected-only lint/type/test selection,
one commit, reading the code before believing a reviewer — I do unprompted and is not listed here.

## What could be cut

- **L326–334** (9 lines) — the Rules block's four step-paraphrase bullets. Zero new invariants,
  and they already disagree with the steps (defect 11). Keep L335 only, relocated.
- **L167–170** (4 lines) — Phase 2 restates the L19–23 table and then says it is "the single spec".
  Reduce to "Triage per the severity table."
- **L178–181** (4 lines) — "Read each finding, open file, make fix" is a pure no-op
  (plugin-authoring L69–70); only "Do NOT commit between fixes" earns its place.
- **L165** — `0 findings → "All green, ready for merge" → STOP.` — no-op.
- **L45–52** (8 lines) — the single-pass paragraph is restated almost whole at L293–298 and again
  at L333–334. Keep one, ~3 lines.
- **L28–36 vs L21–23** — the skip criteria are stated twice with different wording ("Only
  exception: factually wrong" vs a three-item ONLY list); merge into the table's Policy column.
- **L38–43** (6 lines) — finish-first, owned by an always-loaded the host repo rule. One citation line.
- **L217–220** (4 lines) — the blockquote restates L110 and L158–161; and its claim is the source
  of defect 3. Delete and fix once.
- **L13** — "Runs in the main agent (not a subagent) so the user can observe every step" is
  already true of an invoked skill.

Roughly 45–50 of 335 lines are duplication or no-op — before adding the ~10 lines defects 1, 3, 5
and 14 actually require.

## Grade

**2/5** — the thread-collection and 3e gate are genuinely good, but a fresh Opus agent following
this skill literally aborts remote collection in its first tool call (defect 1), can miss the
Claude review entirely under this repo's second bot login (defect 2), and — in exactly the case
this scenario is built around — is authorised to dispute a wrong BLOCKING finding with no place to
record the dispute and is told a green gate will follow, when the gate can never go green.
