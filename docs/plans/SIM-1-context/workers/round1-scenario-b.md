# Round 1 — Scenario B: whole-story worker, parallel_groups in the plan

Simulated as: `worker-DOC-88`, an Agent teammate in the Lead's implicit team, running
`Skill(skill="develop")` for DOC-88 in `/home/dev/acme-DOC-88` on `feat/DOC-88-work`.
Nothing was executed. Every "would call" below is traced against the stated world.

## Trace

### Pre-step: invoking the skill

The brief says `Run: Skill(skill="develop") for DOC-88`. I would call
`Skill(skill="develop", args="DOC-88")`. The skill's `argument-hint` is
`'[<ticket-key> | <plan-path>] [--phases <N,M>] [--engine <name>]'`, so `DOC-88` is a legal
argument. The brief passes no `--phases`, so Step 0's "If absent, run all phases" applies.
No guessing here.

### Step 0 — Locate the plan

- Priority 2 fires (ticket key) → plan path `docs/plans/DOC-88-story.md`. **Guess #1:** relative
  to what? The brief gives `REPO: /home/dev/acme` *and* `WORKTREE: /home/dev/acme-DOC-88`, and
  Step 0 says only `docs/plans/{KEY}-story.md`. The plan lives in the repo; the worktree is on a
  branch cut from `feat/sprint-integration`, so the plan may or may not be present there. I would
  read `/home/dev/acme-DOC-88/docs/plans/DOC-88-story.md` and fall back to
  `/home/dev/acme/docs/plans/DOC-88-story.md`. The skill never says which root.
- `Read("/home/dev/acme-DOC-88/docs/plans/DOC-88-story.md")` → `status: approved`,
  `parallel_groups: [[1, 2], [3]]`, `## Context` 150 words, 3 GWT ACs, three `### Phase` headers.
- Line 35: "Verify the plan has at least one `### Phase` header. If not, stop and tell the user."
  Passes. **Note:** there is no user in a worker session; the only channel out is
  `SendMessage(to="team-lead")`. I would have to translate "tell the user" myself (defect 1).
- Line 37–40: a ticketing tool IS available, so I fetch DOC-88 **with comments**. Per
  `ticketing.md` the tool would be Atlassian MCP → I must first
  `ToolSearch(query="select:mcp__atlassian__jira_get_issue")` (deferred schema), then
  `mcp__atlassian__jira_get_issue(issue_key="DOC-88", comment_limit=20)`. **The skill never
  mentions that ticketing tools are deferred and need a ToolSearch first** — I derived that from
  my own tool listing, not from the skill. World says: no comments beyond the description, which
  matches the plan → no conflict to name.
- **Conflict I had to resolve myself:** the brief says `no ticket transition` and the Lead owns
  ticket state, but Step 0 sends me into the ticketing tool anyway. That is consistent (read vs.
  write) but the skill never says "read-only" — I inferred it from Step 2's last line.

### Step 1 — DoR-lite

Three checks from `dor-scan.md`: GWT ACs (3 present ✓), Context > 50 chars (150 words ✓),
`^### Phase [0-9]+:` (3 ✓). Pass. I would run this as three `grep` calls in the worktree.
Note this re-runs the phase-header check Step 0 already made (defect 9).

### Step 2 — Worktree + branch

Line 54 fires exactly: the brief names a worktree path → `cd /home/dev/acme-DOC-88`, skip
creation, do not call `EnterWorktree`. Clean, and the one place the skill anticipates my
situation precisely. I would run
`Bash("cd /home/dev/acme-DOC-88 && git rev-parse --show-toplevel && git branch --show-current")`
to confirm `feat/DOC-88-work` (the brief demands the `rev-parse` confirmation; the skill does not).
Line 64: "Run the repo's worktree bootstrap from the brief (or `.weside/orchestrate.md`) before any
gate." The brief says "already bootstrapped" and `.weside/orchestrate.md` does not exist →
**no-op**. I had to decide that "already bootstrapped" discharges the instruction; the skill does
not say so.
Line 66: do not transition the ticket. Nothing to do.

### Step 3 — Implement phases

This is where the skill breaks down for this scenario.

- Line 73: "Run phases in the order the plan defines them." Line 75: dispatch groups
  concurrently. `parallel_groups: [[1, 2], [3]]`, no `--phases` filter → both groups are "within
  scope".
- **Can I actually make this call?** I checked my own tool set. `Agent` **is** available to me,
  and `subagent_type="general-purpose"` with `model="sonnet"` is a valid combination. So the
  dispatch is mechanically possible. **But** the Agent tool description states: *"`name` is
  unavailable here — teammates cannot spawn teammates."* So what I spawn are plain subagents, not
  team members: they are not addressable by `SendMessage`, they cannot message the Lead, and they
  return a report only to me. That is fine for this step — but it means the skill's phase
  subagents are structurally different from what `agent-teams.md` describes, and the skill never
  says which shape it wants.
- **Guess #2 — the group boundary.** Nothing in `develop/SKILL.md` says group `[3]` must wait for
  group `[1, 2]` to finish. Only the *Lead's* file says it ("a group runs after every
  lower-numbered phase has merged", orchestrate Step 5.4) and I am not the Lead. World state says
  Phase 3 (`src/docs/cli.py`) depends on both. I would serialize by inference; a worker that reads
  line 75 literally dispatches all three at once and Phase 3 builds against code that does not
  exist yet (defect 2).
- **Guess #3 — `[3]` is a one-element group.** Line 75's condition is satisfied by `[3]`, so the
  literal reading dispatches Phase 3 to a subagent too — a "concurrent" dispatch of one, for a
  phase I could implement inline in less time than the brief takes to write (defect 3).
- **The blocking mechanical problem.** The inlined sub-brief (lines 84–91) tells each subagent:
  *"implement, commit `{KEY}: phase {N} — {description}`, push."* Phase 1 and Phase 2 subagents
  share **one worktree and one branch** (`/home/dev/acme-DOC-88`, `feat/DOC-88-work`) — the skill
  gives them no worktree of their own and no separate branch. Two concurrent agents committing in
  one working tree race on `.git/index.lock`, and two concurrent `git push` on one branch produce
  a non-fast-forward rejection. The skill has **no mechanic** for this (defect 4). I would have
  had to invent one: either give each phase its own worktree (contradicting "do not call
  EnterWorktree" and the Lead's ownership of worktrees), or drop the parallelism and implement
  serially. **I would implement all three phases inline, serially, and say so in the report** —
  the only safe reading.
- Per-phase checklist:
  1. `test_discipline` — line 99 says read `.weside/config.json`, default `tests-after`. The file
     does not exist → default is `tests-after`. **The brief says `tdd`.** The skill never states
     that the brief overrides the config default (defect 5). I would follow the brief (`tdd`), but
     only because the brief is the newer, more specific instruction — not because the skill said so.
     I would write `tests/unit/test_render.py` red first, then `src/docs/render.py`; same for
     Phase 2; then `tests/unit/test_cli.py`-shaped coverage for `src/docs/cli.py`. **Note:** the
     plan's Phase 3 `**Files:**` lists only `src/docs/cli.py` — no test file. Under `tdd` I owe a
     failing test at that seam but the plan's file list forbids the file it would live in. The
     skill has no rule for "test discipline demands a file the plan's list omits" (defect 6).
  2. Wiring check — no new data fields crossing a boundary beyond `render` → `index` → `cli`;
     I would trace it. Real work, correctly asked.
  3. Security check — auth / external APIs / user data: none of the three phases touch any. No-op.
  4. `ruff check --fix` — stack detected as Python from `pyproject.toml`. I would run it. Note
     Step 4's `static-analyzer` runs ruff again (defect 10).
  5. Commit `DOC-88: phase 1 — <description>`. **Guess #4:** with what `git add` scope? The skill
     never says. A naive `git add -A` would sweep in `WORKER-REPORT.md`, which the brief
     explicitly forbids committing. I would `git add` the phase's `**Files:**` by path (defect 7).

### Step 4 — Local quality gates

```python
Agent(subagent_type="we:static-analyzer", ...)
Agent(subagent_type="we:test-runner", ...)
```
Both subagent types exist in my roster, so the calls are makeable — **but the prompts are
literally `...`**. I had to invent both entirely: the worktree path (subagent cwd resets between
bash calls, so an absolute path is mandatory), the Python stack, the ruff/pytest commands, and —
critically — the **fast-tests-only rule**. Lines 118–123 state that rule as prose addressed to
*me*, but the gate is executed by `we:test-runner`, whose own description is "Run tests affected
by current changes" with no notion of skipping DB-backed tests. If I do not inline the
discriminator (`DATABASE_URL`, `REDIS_URL`, `docker-compose up`) into the prompt, the rule is a
no-op (defect 8). The brief also bans `yarn`/`npm install`/`jest`/`tsc` — irrelevant here (pure
Python repo), so **the skipped frontend validation the brief asks me to report is: none, no
frontend in this repo**.
Line 132: *"Do NOT run `/we:ac-review` standalone here — this step runs the same agent inline."*
**False.** Step 4 dispatches `we:static-analyzer` and `we:test-runner`; it does not run
`we:ac-reviewer` at all. That happens in Step 5. I read this line three times before deciding it
was wrong rather than that I had missed something (defect 11).
Gate failures → fix, commit, re-run; 3 in the same gate → circuit-break and report. Clear. World
says nothing surprising, so: green.

### Step 5 — AC-check

`.weside/config.json` absent → `review.cross` defaults to `true` → the AC-check runs.
`Agent(subagent_type="we:ac-reviewer", …)` against **"this worker's diff"**.
**Guess #5 — what diff?** The skill never gives a range. My branch is off
`feat/sprint-integration` per the brief; the skill never tells me to extract the base from the
brief. I would compute `git diff feat/sprint-integration...HEAD` and hope the base ref exists
locally in the worktree (defect 12).
**Ordering contradiction:** `worker-dispatch.md` line 58 and lines 72–74 put the AC-check
*"before committing"* (step 4 of 7, ahead of "5. Commit"). `develop/SKILL.md` commits every phase
in Step 3 and runs the AC-check in Step 5, after the gates — everything is already committed by
then. Two owner documents, two orders (defect 13). I followed the skill's order, being the more
specific document.
World says nothing surprising → AC-check clean.

### Step 6 — Commit and push

`git push origin feat/DOC-88-work`. No `-u`, no `--set-upstream`, no check that the push
succeeded, no `cd` into the worktree in the snippet. The brief says *"NEVER report done without a
pushed branch"* — so I owe a verification the skill does not ask for; I would add
`git ls-remote --heads origin feat/DOC-88-work` (defect 14).

### Step 7 — Report

The skill says "Print a structured report (≤300 tokens). When dispatched by `/we:orchestrate`,
this becomes the worker's `SendMessage`" and gives an eight-line block. The brief gives a
**different, one-line** format with mandatory `to=` and `summary=` fields. The two do not match
and the skill's block has no `SendMessage(...)` call shape at all. I would send the **brief's**
format, since the brief is the contract the Lead parses. Also: `SendMessage` is a **deferred
tool** in my session — I must `ToolSearch(query="select:SendMessage")` before I can call it. The
skill never mentions this; a worker that trusts the skill calls a tool whose schema is not loaded
and gets an `InputValidationError` (defect 15).
**`WORKER-REPORT.md` appears nowhere in the skill.** The brief mandates writing it before
stopping and mandates *not* `git add`-ing it. The skill's Step 7 is titled "Report to the Lead"
and does not mention the file at all (defect 16) — the Lead's own Step 7 monitoring ladder reads
that file as evidence, so a worker following only the skill leaves the Lead blind.
**No stop-early protocol.** Steps 0, 1 and 4 all say "stop" / "report to the Lead" without saying
that stopping means: write `WORKER-REPORT.md`, send exactly one `SendMessage`, then stop
(defect 17).

## Conformance checklist

| Brief requirement | Skill covers it? |
|---|---|
| `cd` to worktree, no `EnterWorktree` | ✅ Step 2 line 54, exactly |
| confirm `git rev-parse --show-toplevel` | ❌ not in the skill |
| implement all phases | ✅ Step 0 "If absent, run all phases" |
| fast local gates | ⚠️ stated to me, not passed to the gate subagent (defect 8) |
| AC-check my diff | ⚠️ yes, but no diff range (defect 12) |
| commit | ⚠️ yes, no `git add` scope (defect 7) |
| push branch, then STOP | ✅ Steps 6 + Rules; push unverified (defect 14) |
| no PR / CI / ticket transition / doc pass | ✅ stated four times over (defect 18) |
| FINISH FIRST ladder | ✅ Rules line 200, faithful to the brief |
| questions to the Lead, never tickets | ✅ line 200 |
| `tdd` | ⚠️ skill defaults to `tests-after` from an absent config; no override rule (defect 5) |
| report skipped frontend validation | ❌ never mentioned |
| write `WORKER-REPORT.md`, do not `git add` it | ❌ absent entirely (defect 16) |
| exactly one `SendMessage` in the given format | ❌ different format, no tool-name, no ToolSearch note (defect 15) |
| never report done without a pushed branch | ❌ not in the skill |

## Skill defects

1. `[CLARITY]` — line 35 `"Verify the plan has at least one \`### Phase\` header. If not, stop and tell the user."` and line 39 `"you name the conflict to the user"` — there is no user in a dispatched worker session; the only channel out is `SendMessage(to="team-lead")`. Fix: say "report to the Lead" everywhere the worker path speaks to a human.

2. `[MISSING MECHANIC]` — line 75 `"if \`parallel_groups\` declares a group and all phases in the group are within scope (\`--phases\` filter), dispatch them concurrently with one \`Agent()\` call per phase in a single message"` — nothing says a later group waits for an earlier one to finish, so a literal reading dispatches Phase 3 (which depends on 1 and 2) against code that does not exist. Fix: state "groups run in order; the next group starts only after every phase of the previous one is committed."

3. `[CLARITY]` — same line 75: a one-element group like `[3]` satisfies "declares a group", so the rule dispatches a subagent to run a single phase concurrently with nothing. Fix: "a group of one runs inline."

4. `[MISSING MECHANIC]` — lines 84–91, `"Instruction: implement, commit \`{KEY}: phase {N} — {description}\`, push."`— the concurrent phase subagents are given no worktree and no branch of their own, so two of them commit into one working tree (`.git/index.lock` race) and push one branch (non-fast-forward). Fix: either give each parallel phase its own worktree/branch and say who merges them, or restrict parallel dispatch to phases that do not commit and have the parent commit once.

5. `[CLARITY]` — line 99 `"apply the configured test discipline (\`test_discipline\` from \`.weside/config.json\`, default \`tests-after\`…)"` vs. the Lead brief's `TESTS: tdd` — the skill never says the brief's level overrides the config default, so a worker with no config file silently drops to `tests-after` against an explicit `tdd` instruction. Fix: "the Lead's brief takes precedence over `.weside/config.json`; config is the fallback."

6. `[MISSING MECHANIC]` — line 99 again, combined with the plan's per-phase `**Files:**`: under `tdd` a seam owes a failing test first, but Phase 3's file list names only `src/docs/cli.py`, and Rules line 200 forbids expanding scope. Fix: state that a test file required by the discipline is always in scope even when the plan's file list omits it.

7. `[MISSING MECHANIC]` — line 103 `"Commit: \`{KEY}: phase {N} — {description}\`"` gives no `git add` scope, and the Lead's brief separately forbids committing `WORKER-REPORT.md`. A worker that reaches for`git add -A` breaks the brief. Fix: "stage the phase's `**Files:**` by path; never `git add -A`."

8. `[MISSING MECHANIC]` — lines 114–123: the fast-tests-only rule and its discriminator (`DATABASE_URL`, `REDIS_URL`, `docker-compose up`) are addressed to the reader, but the gate runs in `Agent(subagent_type="we:test-runner", ...)`, which never sees them. Fix: put the discriminator inside the dispatch prompt template, not in prose beside it.

9. `[CUT]` — Step 1's third scan item duplicates line 35's `"Verify the plan has at least one \`### Phase\` header"`, checked two steps apart with two different stop instructions. Fix: drop line 35 and let the DoR-lite scan own it.

10. `[CUT]` — line 102 `"Run auto-fix for the detected stack: \`ruff check --fix\` / \`eslint --fix\` / \`gofmt\` / \`rustfmt\`"` — Step 4's `we:static-analyzer` runs lint and format anyway, and any competent worker runs the formatter before committing. Fix: delete; let the gate own it.

11. `[CLARITY]` — line 132 `"**Do NOT run \`/we:ac-review\` standalone here** — this step runs the same agent inline"` — factually wrong: Step 4 dispatches `static-analyzer` and `test-runner` only; the AC-review agent runs in Step 5. Fix: move the sentence to Step 5 or delete it.

12. `[MISSING MECHANIC]` — line 143 `"Run \`we:ac-reviewer\` against **this worker's diff** (not the full branch)"` — no diff range is given and the worker is never told to take the base ref from the Lead's brief. Fix: `git diff {integration_branch}...HEAD`, with the integration branch named as coming from the brief.

13. `[CLARITY]` — `develop/SKILL.md` orders commit-per-phase (line 103) → gates (Step 4) → AC-check (Step 5), while `worker-dispatch.md` line 58 lists `"4. **AC-check own diff**"` before `"5. **Commit**"` and line 73 says *"before committing"*. Two owner documents, two orders. Fix: pick one and delete the other statement.

14. `[MISSING MECHANIC]` — line 166 `"git push origin {branch-name}"` — no upstream flag, no success check, while the brief says *"NEVER report done without a pushed branch."* Fix: add `git push -u origin {branch}` plus a `git ls-remote --heads origin {branch}` verification before Step 7.

15. `[MISSING MECHANIC]` — line 173 `"Print a structured report (≤300 tokens). When dispatched by \`/we:orchestrate\`, this becomes the worker's \`SendMessage\`"` followed by an eight-line block that is not the brief's one-line format and contains no `SendMessage(to=…, summary=…)` call. `SendMessage` is also a deferred tool needing a `ToolSearch` first. Fix: show the literal `SendMessage(to="team-lead", summary=…, message=…)` call in the brief's format, and note the ToolSearch.

16. `[MISSING MECHANIC]` — `WORKER-REPORT.md` appears nowhere in `develop/SKILL.md`, yet the Lead's brief mandates it and the Lead's own monitoring ladder reads it as liveness evidence. Fix: add it to Step 7 — write it, never `git add` it.

17. `[MISSING MECHANIC]` — line 35 `"stop and tell the user"`, line 47 `"If any item fails, stop and say which"`, line 130 `"3 failures in the same gate → stop, report to the Lead"` — three stop paths, none of which says what stopping consists of (report file + exactly one message + stop). Fix: one "Stopping early" block naming the three actions, referenced from all three.

18. `[CUT]` — the dev-only contract is stated four times: the frontmatter description, line 16 `"You do not run the integration pipeline: no PR, no CI fix loop, no ticket transition."`, line 195 `"**Stop after push.** No PR, no per-worker CI loop, no ticket transition."`, and line 199 `"**Never dispatch a nested pipeline**"`. Fix: keep line 195, delete the other three.

19. `[CUT]` — line 202 `"**Model tier defaults:** sonnet for normal phases, haiku for mechanical, opus only when the Lead explicitly requests it"` is a verbatim restatement of line 105, and both are moot for a worker whose Lead already picked the tier. Fix: delete line 202.

20. `[CLARITY]` — line 89 `"the sub-agent cannot load references"` is false for Claude subagents: they inherit the filesystem and have `Read`. The instruction to inline the anti-pattern list is right for a *foreign engine*, wrong as a stated reason here. Fix: say "inline it so the brief is self-contained across backends", or just give the subagent the path.

21. `[CLARITY]` — line 64 `"Run the repo's worktree bootstrap from the brief (or \`.weside/orchestrate.md\`) before any gate"` is a silent no-op when the brief says "already bootstrapped" and no `.weside/orchestrate.md` exists (this scenario). Fix: "…unless the brief states the worktree is already bootstrapped."

22. `[CLARITY]` — line 30 points at `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py`, and lines 20/126/145 at `${CLAUDE_PLUGIN_ROOT}/references/…`. A worker has no stated guarantee that `CLAUDE_PLUGIN_ROOT` is exported in its Bash environment, and no fallback is given. Fix: name the fallback (resolve relative to the skill file) or drop the script path from the worker lane.

## What I needed and did not find

- **A worktree/branch model for concurrent phase subagents.** The single largest hole. Scenario B's `parallel_groups` is exactly the feature this skill advertises, and following it literally corrupts the git index. I could not derive a safe answer from the skill and fell back to serial implementation.
- **Group ordering.** Not stated in the worker's own file; only in the Lead's.
- **Precedence between the Lead's brief and `.weside/config.json`.** Needed for `tdd`. Guessed.
- **The diff range for the AC-check.** Needed the integration branch name; the skill never routes it from the brief.
- **`WORKER-REPORT.md` and the stop-early protocol.** Both are in the brief, neither in the skill. A worker running `/we:develop` from a plain user invocation would never write the file.
- **The exact `SendMessage` shape and that it needs a `ToolSearch` first.**
- **`git add` scope for phase commits.**
- **Which root `docs/plans/` is relative to** when repo root and worktree differ.
- **How to report a "nothing to skip" case** — the brief asks for the skipped frontend validation; there is no frontend. The skill's report template has no slot for the brief's `skipped:` field at all.

## Grade

**2/5.** The skill's spine is right and Step 2's worktree branch is written by someone who has
actually been dispatched by this Lead — it handles the pre-created-worktree case precisely and
the FINISH FIRST ladder in Rules is a faithful, load-bearing copy of the brief. But this scenario
is the skill's own headline feature (`parallel_groups`) and the skill cannot carry it: the
concurrent dispatch template hands two agents one worktree and one branch with instructions to
commit and push, gives no group ordering, and treats a one-phase group as a parallel group. Below
that, three of the seven steps have holes I had to fill from the brief rather than the skill —
the gate dispatch prompts are literally `...` with the fast-tests rule stranded in prose the gate
agent never reads; the AC-check has no diff range; and the entire report contract the Lead
actually depends on (`WORKER-REPORT.md`, the one-line `SendMessage`, "never report done without a
pushed branch") lives only in the brief, so `/we:develop` invoked by a human produces none of it.
Two documents contradict each other on when the AC-check runs, and one line (132) is simply
false. A fresh worker cannot follow this without inventing steps; I invented at least five, one
of which (serial instead of parallel) contradicts the skill's explicit instruction and is the
only reason the run would not corrupt its own tree.
