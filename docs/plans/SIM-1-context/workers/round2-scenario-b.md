# Round 2 — Scenario B: whole-story worker, parallel_groups in the plan

Re-simulated as `worker-DOC-88`, an Agent teammate in the Lead's implicit team, running
`Skill(skill="develop")` for DOC-88 in `/home/dev/acme-DOC-88` on `feat/DOC-88-work`.
Nothing executed. Every "would call" is traced against the revised
`we/skills/develop/SKILL.md` (194 lines, Steps 0–6).

## Trace (revised skill)

### Pre-step: invocation

`Skill(skill="develop", args="DOC-88")`. `argument-hint` is unchanged
(`'[<ticket-key> | <plan-path>] [--phases <N,M>] [--engine <name>]'`), the brief passes no
`--phases`, and line 43 settles it: *"`--phases N,M`: implement only those `### Phase` blocks.
Absent → all phases."* I own phases 1, 2 and 3.

Before Step 0 the skill hands me three things round 1 had to invent:

- Line 19: *"**The Lead's brief outranks every default in this skill.** Where the brief names a
  worktree, branch, test discipline, gate list or integration suite, that value wins over
  `.weside/config.json` and over the steps below; you name the override in your report."*
- Line 25: *"**You are talking to the Lead, not a user.** Dispatched, your printed output is
  invisible: the only channels out are `WORKER-REPORT.md` and exactly one `SendMessage`
  (Step 6)."*
- Line 29: *"**Stopping early** — at any stop below, do all three: write `WORKER-REPORT.md` with
  what you completed and why you stopped, send the one message with `blocked: <reason>`, stop.
  A stop without a message is a chunk the Lead waits on forever."*

That is three of round 1's largest holes closed in the first thirty lines, before any step runs.

### Step 0 — Locate the plan

Priority 2 fires: *"Ticket key → `docs/plans/{KEY}-story.md` (relative to the repo root the brief
names, not the worktree, when they differ)"* (lines 38–39). Round 1's "which root?" guess is gone —
I read `/home/dev/acme/docs/plans/DOC-88-story.md`. Deterministic, even if it means the plan I read
is main's copy while I build in the worktree; the skill made the call, so I do not have to.

DoR-lite is now conditional: *"**Standalone invocation only** (no Lead brief): run the 3-item scan
… A briefed worker skips it — the Lead ran it before dispatch"* (lines 45–47). I am briefed → I
skip it. The round-1 duplication with a separate phase-header check in Step 0 is gone; that check
now exists only inside `dor-scan.md`, which I never load.

Ticket read (lines 49–54): a ticketing tool is available → I fetch DOC-88 **with comments**. Per
`ticketing.md` that is Atlassian MCP `jira_get_issue(comment_limit=…)`, still a deferred tool
needing `ToolSearch` first — the skill flags deferral for `SendMessage` (line 164) but not here.
Minor; I derive it from my own tool listing. World says comments match the plan → nothing to
escalate. Line 53 gives me the escalation rule I lacked: *"A comment that **changes scope** after
the plan was approved … is not yours to absorb — stop and hand it back as a question."*

### Step 1 — Worktree + branch

Line 60 fires exactly: *"**Brief names a worktree path** … `cd` there, do not call
`EnterWorktree`. Run the bootstrap the brief names, unless it says the worktree is already
bootstrapped."* The brief says bootstrapped → discharged in writing, not by my inference.
Line 67: *"Do **not** transition the ticket."* Nothing to do.

The brief's `git rev-parse --show-toplevel` confirmation is still not in the skill — I run it
because the brief demands it. Unnumbered in round 1, unchanged here, and harmless: the brief
carries it.

### Step 2 — Implement phases

This is the step that broke in round 1. It no longer does:

> Read the plan completely and implement its phases **in the order the plan defines them,
> inline**. Never fan out to sub-agents: phases in one worktree share one git index, so two
> concurrent committers race `.git/index.lock` and push the same branch. (lines 73–75)

Round-1 defects 2, 3 and 4 die together with the concurrent-dispatch template. Plan order is
1 → 2 → 3, which is exactly what Phase 3's dependency on `render.py` and `index.py` requires. No
inference needed, no index race, no invented worktree model.

Per-phase, the checklist now carries what I had to guess:

1. Line 81: *"Apply the test discipline the brief names (`.weside/config.json`'s
   `test_discipline` is the fallback, default `tests-after`)"* — with the preamble's override
   sentence naming "test discipline" explicitly, `TESTS: tdd` from the brief wins **by rule**, not
   by my judgement. Config file absent, irrelevant.
2. Line 84: *"A test file the discipline requires is in scope even when the plan's `**Files:**`
   omits it."* This is the exact Phase-3 case — the plan lists only `src/docs/cli.py`, `tdd` owes
   a failing test at that seam, and I may now write `tests/unit/test_cli.py` without breaching the
   scope rule.
3. Wiring check (line 85) — `render` → `index` → `cli`, real work, I trace it.
4. Security check (line 87) — no auth, no external APIs, no user data. No-op.
5. Generated artifacts (line 88) — the brief lists none. No-op.
6. Line 90: *"Stage the phase's files **by path** — never `git add -A`, which would sweep
   `WORKER-REPORT.md` into the diff."* Round-1 defect 7 closed, and closed with the brief's own
   reason attached.

Commit template (lines 93–97) is `{KEY}: phase {N} — {description}` plus
`Co-Authored-By: <Engine> <Model> <noreply@…>` — see new defect N1.

Line 76: *"`parallel_groups` is the Lead's tool for splitting phases across separate worker
worktrees — a phase grouped with yours may be building right now, so treat any file listed under
it as a shared seam and say so in your report."* Read literally against my scope, this fires and
is wrong — see new defect N2. I would not report `render.py`/`index.py`/`cli.py` as shared seams,
because I own all three.

### Step 3 — Local quality gates

The `...` prompts are gone. Both dispatches are written out (lines 105–113), carry `{branch}` and
`{worktree}`, and the fast-tests rule is now **inside** the prompt the gate agent reads:

> "Run only unit and fast smoke tests for the changes on {branch} in {worktree}. SKIP any test
> needing DATABASE_URL, REDIS_URL, a queue, an HTTP service or docker-compose, and list what you
> skipped. Do not run `yarn`/`npm install`, `jest` or `tsc` in a worktree without node_modules —
> report that as skipped."

Round-1 defect 8 is closed at the seam that mattered: `we:test-runner` now receives the
discriminator instead of it sitting in prose addressed to me. The node clause also answers the
brief's "report the skipped frontend validation" — pure-Python repo, so the honest answer is
"none, no frontend", and line 169's `"skipped: … (or none)"` gives that answer a slot.

The critical-chunk exception (lines 116–118) does not apply: docs rendering is not money, auth,
tenant isolation or a migration, and the brief bans DB tests outright. Circuit breaker at 3
failures in one gate (line 122), and the preamble now tells me what "stop" costs. World says
green.

### Step 4 — AC-check

Brief orders it → runs regardless of the absent `.weside/config.json` (lines 129–130). The diff
range exists now:

> `Agent(subagent_type="we:ac-reviewer", prompt="Check \`git diff {integration_branch}...HEAD\`
> against the ACs docs/plans/{KEY}-story.md Phase {N} claims to satisfy. Findings only.")`
> … "The integration branch comes from the brief; standalone, use the branch you cut from."

`feat/sprint-integration` from the brief → `git diff feat/sprint-integration...HEAD`. Round-1
defect 12 closed. `Phase {N}` singular is a new snag (defect N3), and the *ordering* against the
brief is not (defect N4).

### Step 5 — Push

`git push -u origin {branch} && git ls-remote --heads origin {branch}` (line 151), with line 154:
*"An empty `ls-remote` means the push did not land — that is a blocker, not a done."* Exactly the
verification round 1 had to add from the brief.

### Step 6 — Report

Line 160: write `WORKER-REPORT.md`, *"It is not part of the change: never `git add` it."* Line
164: *"(`SendMessage` is a deferred tool — `ToolSearch` for it first)"*, then the literal call in
the brief's shape with `to=`, `summary=` and the pipe-separated fields. Both of round 1's blind
spots closed, and the deferred-tool note is there.

The skill's message adds `questions: …`, which the brief's format omits. Superset, not conflict —
I would send the brief's fields plus that one, since Rules line 186 routes questions to the Lead
and there is nowhere else to put them.

### Outcome

I would implement three phases serially, tdd, inline; commit three times by path; run both gate
agents in one message; AC-check against `feat/sprint-integration...HEAD`; push with verification;
write the report file; send one message. **Zero invented steps that touch git.** Round 1 invented
five, one of which contradicted the skill.

## Round-1 verdict table

| # | Round-1 defect (short) | Verdict | Evidence (quoted line or its absence) |
|---|---|---|---|
| 1 | "tell the user" in a worker session | **FIXED** | L25 *"**You are talking to the Lead, not a user.** … the only channels out are `WORKER-REPORT.md` and exactly one `SendMessage`"*; L51 *"record the conflict in your report"*; no "user" remains on a worker path |
| 2 | No group ordering → Phase 3 dispatched against absent code | **FIXED** | L73 *"implement its phases **in the order the plan defines them, inline**"*; the concurrent-dispatch rule is deleted |
| 3 | One-element group `[3]` dispatched "concurrently" | **FIXED** | Same deletion — L74 *"Never fan out to sub-agents"* |
| 4 | Concurrent phase agents share one worktree + branch | **FIXED** | L74 *"phases in one worktree share one git index, so two concurrent committers race `.git/index.lock` and push the same branch"* — the hazard is now the stated reason for the rule |
| 5 | Brief's `tdd` vs config default `tests-after` | **FIXED** | L19 *"Where the brief names a worktree, branch, **test discipline**, gate list or integration suite, that value wins over `.weside/config.json`"*; L81 *"Apply the test discipline the brief names"* |
| 6 | tdd owes a test file the plan's `**Files:**` omits | **FIXED** | L84 *"A test file the discipline requires is in scope even when the plan's `**Files:**` omits it."* |
| 7 | No `git add` scope; `-A` would commit `WORKER-REPORT.md` | **FIXED** | L90 *"Stage the phase's files **by path** — never `git add -A`, which would sweep `WORKER-REPORT.md` into the diff."* |
| 8 | Fast-tests rule in prose the gate agent never reads | **FIXED** | L111 inside the prompt: *"SKIP any test needing DATABASE_URL, REDIS_URL, a queue, an HTTP service or docker-compose, and list what you skipped."* |
| 9 | Phase-header check duplicated across Step 0 and Step 1 | **FIXED** | Step 0 has no phase-header check; the scan is L45 *"**Standalone invocation only** … A briefed worker skips it"* |
| 10 | `ruff check --fix` duplicating `we:static-analyzer` | **FIXED** | The per-phase auto-fix item is gone; L106 `we:static-analyzer` is the only lint/format owner |
| 11 | Line 132 falsely claimed Step 4 ran the AC agent | **FIXED** | The sentence now sits in the step that does run it — L140 *"Do **not** run `/we:ac-review` as a separate pass"*, inside Step 4 |
| 12 | AC-check had no diff range | **FIXED** | L134 *"Check `git diff {integration_branch}...HEAD`"*; L138 *"The integration branch comes from the brief; standalone, use the branch you cut from."* |
| 13 | SKILL commits-then-AC-checks; `worker-dispatch.md` says AC-check first | **STILL OPEN** | `worker-dispatch.md` L57–58 still *"4. **AC-check own diff** … 5. **Commit**"* and L72–73 *"against the worker's own diff, **before committing**"*, against SKILL L90 (commit in Step 2) and L139 *"fix what you own, commit it (`{KEY}: AC-check fixes`)"* in Step 4. The preamble ranks the *brief* over the skill; nothing ranks the skill over its references |
| 14 | Push unverified, no upstream | **FIXED** | L151 `git push -u origin {branch} && git ls-remote --heads origin {branch}`; L154 *"An empty `ls-remote` means the push did not land — that is a blocker, not a done."* |
| 15 | Report block was not a `SendMessage` call; no deferred-tool note | **FIXED** | L164 *"(`SendMessage` is a deferred tool — `ToolSearch` for it first)"* + the literal `SendMessage(to="team-lead", summary=…, message=…)` in the brief's field order |
| 16 | `WORKER-REPORT.md` absent from the skill | **FIXED** | L160 *"Write `WORKER-REPORT.md` in the worktree root … It is not part of the change: never `git add` it."* |
| 17 | Three stop paths, no stop protocol | **FIXED** | L29 *"at any stop below, do all three: write `WORKER-REPORT.md` …, send the one message with `blocked: <reason>`, stop"* |
| 18 | Dev-only contract stated four times | **PARTIALLY** | Down from four to three: frontmatter `description`, L14 *"No PR, no CI fix loop, no ticket transition"*, and Rules L179 *"**Stop after push.** No PR, no per-worker CI loop, no ticket transition, no nested pipeline"*. The old fourth (nested pipeline) was folded into L179; the intro and the rule still say the same thing twice |
| 19 | Model-tier defaults stated twice, moot for a worker | **FIXED** | No model-tier line survives in the skill; L191 delegates it — *"`worker-dispatch.md` — full dispatch contract, AC-review rule, **model tiers**"* |
| 20 | "the sub-agent cannot load references" is false | **PARTIALLY** | Gone from the skill with the sub-agent dispatch, but the false claim survives where it now contradicts the skill: `worker-dispatch.md` L54 *"workers can't load references"* and `test-discipline.md` L7 *"worker briefs (which inline the level — workers can't load references)"*, while SKILL L83 sends me to read `test-discipline.md` |
| 21 | Bootstrap instruction a silent no-op | **FIXED** | L62 *"Run the bootstrap the brief names, **unless it says the worktree is already bootstrapped**."* |
| 22 | `${CLAUDE_PLUGIN_ROOT}` unguaranteed, no fallback | **STILL OPEN** | Still used at L40 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story status`, L46, L50, L83, L143, L191–193; no fallback stated anywhere. The markdown links carry a relative twin (`../../references/…`), but L40's script path has none, and the relative path is never named as the fallback |

**Tally: 18 FIXED · 2 PARTIALLY · 2 STILL OPEN.**

Two unnumbered round-1 gaps also closed, both from *"What I needed and did not find"*: the
nothing-to-skip case now has a slot — L169 *"skipped: … (or none)"* — and the plan root is settled
at L38 *"relative to the repo root the brief names, not the worktree, when they differ"*.

## New defects introduced by the revision

**N1 `[MISSING MECHANIC]` — the commit trailer is an unresolvable placeholder.** L96:
`Co-Authored-By: <Engine> <Model> <noreply@…>`. Nothing tells a worker what to substitute — its
own engine name, the Lead's, the model id, which address. Round 1 quoted the commit instruction
(then L103) without a trailer, so I cannot claim the revision introduced it; new or missed, it is
unresolved either way, and `orchestrate` SKILL relies on the trailer (*"Every worker commit
carries `Co-Authored-By: <Engine> <Model> <noreply@…>`"*) as the record of who wrote what. Fix:
one line naming the substitution — the engine and model executing this skill.

**N2 `[MISSING MECHANIC]` — the `parallel_groups` note fires backwards in exactly this scenario.**
L76: *"a phase grouped with yours may be building right now, so treat any file listed under it as
a shared seam and say so in your report."* I own **every** phase in **every** group, so the
grouping is inert and the instruction read literally has me report `render.py`, `index.py` and
`cli.py` as shared seams that nobody shares. The inverse case is unhandled too: `orchestrate`
SKILL L477 says *"`parallel_groups` in the frontmatter means you should have run Mode B — note
it"*, so a single whole-story worker dispatched against a plan carrying `parallel_groups` is a
Lead-side dispatch error, and L75–77 is the only place a worker could catch it — yet nothing tells
me to hand it back as a question. Fix: split the case — *"you own every phase in every group → the
grouping is inert; say so and flag the dispatch to the Lead. You own only some → the other group's
files are a shared seam."*

**N3 `[CLARITY]` — the AC-check prompt is written for a single phase.** L135: *"against the ACs
docs/plans/{KEY}-story.md **Phase {N}** claims to satisfy."* The skill's own default is all phases
(L43), and this worker owns three. `{N}` has no value to substitute; I would write "Phases 1–3"
and hope that is what was meant. Fix: `Phase(s) {phases-in-scope}`, or drop the phase clause and
name the diff.

**N4 `[CLARITY]` — the brief and the skill disagree on when to commit, and the override list does
not cover ordering.** The brief's order is *"implement all phases → fast local gates → AC-check
your diff → commit → push"*; the skill commits per phase in Step 2, gates in Step 3, AC-checks in
Step 4. L19's precedence clause enumerates *"a worktree, branch, test discipline, gate list or
integration suite"* — ordering is not on that list, so nothing settles it. This is the sharper,
worker-facing form of still-open defect 13: three documents (brief, skill, `worker-dispatch.md`)
carry three positions on the same question. Fix: state that the skill's step order is the
executed one and delete the "before committing" claims from `worker-dispatch.md`, or add ordering
to L19's list.

**N5 `[CLARITY]` — "Never fan out to sub-agents" (L74) is contradicted two steps later** by the
three `Agent(...)` dispatches in Steps 3 and 4. The trailing reason clause ("phases in one
worktree share one git index") scopes it to phases, so I resolved it correctly, but the bare
sentence reads absolute. Fix: *"Never fan out **phases** to sub-agents."*

## Grade

**4/5.** The revision is the rare kind that gets shorter and stronger at once: round 1 quoted a
line 227, so the old file ran to at least 227 lines; this one is 194 with Steps 0–7 consolidated
to 0–6 and roughly eight mechanics *added* — the stop protocol, the report file, the literal
`SendMessage` with its deferred-tool note, the `git add` scope, the diff range, the push
verification, the brief-over-config precedence, and the test-file-in-scope rule. The remaining
length earns itself; I could not point at a paragraph a fresh worker skips. The headline fix is
that the skill stopped advertising a feature it could not carry: deleting the concurrent phase
dispatch kills four round-1 defects at once and replaces them with a stated hazard, so this run
would produce no invented git behaviour at all where round 1 invented five steps and had to
contradict the skill to stay safe. It falls short of 5 on the seam between the skill and its own
references — `worker-dispatch.md` still orders the AC-check before the commit and still asserts
that workers cannot load the references the skill sends them to read — and on three small
substitutions a worker must resolve alone: the `Co-Authored-By` placeholder, `Phase {N}` for a
three-phase chunk, and `${CLAUDE_PLUGIN_ROOT}` with no fallback. And in the one scenario named for
`parallel_groups`, the single line the skill still spends on it fires in the wrong direction: it
warns me about a seam I own outright and stays silent about the dispatch error I am the only one
positioned to notice.
