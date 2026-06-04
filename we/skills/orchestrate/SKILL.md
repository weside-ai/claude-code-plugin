---
name: orchestrate
description: >
  Epic-driven build orchestration. The Lead boots from state like a colleague —
  reconstructs where an Epic stands from its plans, frontmatter, ticketing mirror,
  and build-state — computes the ready set of buildable Stories, and (on confirm)
  dispatches one builder-teammate per Story running the full /we:build, tracking
  each in the shared task-list + orchestration DB. The Build-altitude sibling of
  /we:council. Use when the user says "/we:orchestrate", "orchestrate the epic",
  "dispatch the ready stories", "run the builds", "kick off the ready builds". For a
  read-only status snapshot of an Epic, use /we:epic instead — orchestrate is the
  dispatch-altitude sibling that actually spawns builders.
---

# /we:orchestrate

**Purpose:** Stop being the manual courier between a planning session and per-Story build
sessions. The Lead — the session running `/we:orchestrate` — is a persistent colleague that
boots knowing where the Epic stands, holds context, computes which Stories are ready to build,
dispatches them as watchable/steerable **builder-teammates** (Agent Teams), tracks start/end
automatically, and reviews each finished PR. It never merges — Deliver stays human.

This is the **Build-altitude sibling of `/we:council`/`/we:meet`**: the same Agent-Teams
machinery (`TeamCreate` → `Agent(team_name=…, name=…)` → `SendMessage` → `TeamDelete`), but the
teammates are **builders** running `/we:build`, not deliberators.

> **Spike status (WA-1231).** This skill is a spike: it proves the dispatch+tracking loop on
> one real Epic with a **hard cap of ≤2 concurrent builders**. The full orchestrator (parallel
> dispatch beyond 2, cross-Story circuit breakers, resume) is gated on this spike's go/no-go.
> Design + evidence: `weside-core/docs/plans/WA-1231-design.md`.

## Prerequisites

Agent Teams must be enabled — same flag as `/we:council`. In `~/.claude/settings.json`:

```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

A session restart is needed after toggling. If the flag is missing when dispatch runs, the
skill aborts in Step 4 with a remediation hint — there is no non-team fallback.

## Invocation

```
/we:orchestrate <epic>              # boot + status + ready-set; dispatch only on confirm
/we:orchestrate <epic> --rehearsal  # run the pipeline against a fixture, no real PR/ticket
/we:orchestrate                     # boot from the most recently active epic, then status
```

`<epic>` is an Epic **slug** (e.g. `circles`) or a ticketing Epic key (e.g. `WA-1205`) — either
works. Stories may reference their epic by slug or by key; `story ready` resolves both via the
Epic plan's `epic:`/`ticket:` frontmatter (`_resolve_epic_identifiers`).

---

## Workflow

### Step 1: Boot from state (always — this is the colleague's first act)

Before anything else, reconstruct "where we stand". Read the **living** files so the picture is
always current — never rely on cached knowledge:

1. **Epic frame** — read the Epic plan `docs/plans/*<epic>*-epic.md` if one exists; its
   `## Success Criteria` / scope are the lens for "what done means". If there is no epic file
   (and no Saga mirror row), **degrade gracefully**: synthesise the frame from the child
   Stories that share this `epic:` slug — do not abort. An epic slug backed only by Story plans
   is valid (a rehearsal or a freshly-cut epic).
2. **Child Stories** — glob `docs/plans/*-story.md`, keep those whose frontmatter `epic:`
   matches `<epic>`. For each, read frontmatter (`story`, `status`) and scan the body for DoR
   completeness (GWT ACs present, Context non-empty, `### Phase` headers — same gate `/we:build`
   Step 1 uses).
3. **Ticketing mirror** — if a ticketing tool is available (weside MCP `JIRA_*` → Atlassian MCP
   → `gh`), fetch each Story's ticket status. No ticketing tool → use plan frontmatter `status`
   only (same fallback as `/we:epic`).
4. **Build state** — for each Story key, run
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story status {TICKET}` to read its
   pipeline phase / last checkpoint / PR number.
5. **Handoff** — if `docs/handoffs/` has a recent entry for this Epic, read the latest; it
   carries decisions/next-steps the files don't.

Render a tight **"here is where we stand"** snapshot: Epic name, and per Story a line with
`{key} {title} — plan:{refined|incomplete|missing} ticket:{status} build:{phase|—} pr:{#|—}`.

Then **stay open** as the conversational partner. If the user only asked status (or `/we:orchestrate`
with no clear go), present the snapshot + the ready-set (Step 2) and **wait** — answer "where are
we / what's next" from this reconstructed stand. Do not dispatch without an explicit go.

### Step 2: Compute the ready set (pure, explainable)

A Story is **ready** iff ALL hold; otherwise it is **held** with the first failing reason:

| Rule | Ready needs | Held reason if it fails |
|---|---|---|
| Refined plan | plan file exists AND passes the DoR scan (GWT ACs, Context, Phase headers) | `no refined plan` |
| Not built | no `pr_created`/`ci_passed` checkpoint AND ticket not already In Review/Done | `already built` |
| Dependencies met | every declared dependency Story is built/merged | `waiting on {dep}` |
| Cap | fewer than the spike cap (2) already dispatched this run | `cap reached` |

The rules are computed by a tested pure helper — **call it, do not re-derive them**:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story ready <epic> --plans-dir docs/plans
```

It returns `{"ready": [...], "held": [{"key", "reason"}]}` by applying exactly the rules above
(`compute_ready_set` in `orchestration.py`, unit-tested in `test_ready_set.py`). Render its two
lists as **READY** (would dispatch) and **HELD** (with each reason). The table above is the
spec, the CLI is the implementation — they must not drift.

### Step 3: Confirm gate (human-in-the-loop)

Present the ready set and ask the user to confirm dispatch. This is the first of three human
gates (the others: Lead reviews each PR in Step 8; human merges). **Never dispatch without an
explicit confirm.** If `--rehearsal`, skip to the Rehearsal section instead.

### Step 4: Preflight

1. **Env-flag check** — confirm `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. If missing, abort:

   ```
   /we:orchestrate needs Agent Teams enabled.

   Add this to ~/.claude/settings.json:
     { "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
   Then restart your session. Or run /we:setup — it sets the flag for you.
   ```

2. **Runaway guard (mandatory)** — never dispatch more than **2** builders concurrently. If the
   ready set is larger, dispatch the first 2 (lowest Story key first) and **log** that the rest
   were held by the cap. Refuse, loudly, any attempt to exceed it.

3. **Lead voice (MCP, optional)** — if `mcp__plugin_we_weside-mcp__get_council` exists, call it
   once for the Lead's review role (`product_owner` or `architect`, per `.weside/config.json`)
   and adopt that Companion's `identity_prompt` for the Lead's review voice in Step 8. Builders
   get **no** identity (the weside backend is user-scoped — parallel `select_companion` races;
   see `/we:council` "Memory in v1"). No MCP → generic review lens. Degrade gracefully.

4. **Generate `team_name`** — `orchestrate-<epic>-<HHMMSS>`, unique per session.

### Step 5: Open the team

```python
TeamCreate(team_name=<generated>, description=f"Orchestrate epic: {epic}")
```

The Lead session is automatically the team lead. Only the Lead can later `TeamDelete`.

### Step 6: Dispatch builders (all spawns in one message) + record start

For each ready Story (≤2), create a task and spawn a builder-teammate. **All `Agent` spawns go
into a single assistant message** so they initialize concurrently.

```python
TaskCreate(subject=f"Build {TICKET}", description=f"Run /we:build {TICKET} to a reviewable PR.")
Agent(
    team_name=<team_name>,
    name=f"builder-{TICKET}",
    subagent_type="general-purpose",
    model="sonnet",
    description=f"Build {TICKET}",
    prompt=<Builder-Brief — see below>,
)
```

The shared task-list (the `TaskCreate` above) carries the **live** dispatched/in-flight state.
The **durable** start/end record needs no orchestrator write: the builder's own `/we:build`
writes `story_workflow` rows into `orchestration.py` automatically — `git_prepared` on start,
`pr_created`/`ci_passed` on end (this is the single-writer that satisfies AC3). The Lead
**reads** them via `story status` for the roll-up; it does not write build checkpoints itself.

**Builder-Brief** (self-contained — the builder runs the full, unmodified build):

```
You are builder-{TICKET}, a teammate in team {team_name}. The lead is "team-lead".

REPO: your working repo is {repo_root} (the Lead's repo). Teammates inherit the Lead's cwd,
which the shell may reset between commands — so START EVERY bash command with `cd {repo_root}`,
and confirm `git rev-parse --show-toplevel` is {repo_root} before any git operation. NEVER let
EnterWorktree or a quality-gate subagent run against a different repo.

ISOLATION: create your own worktree so concurrent builders never share a working tree —
EnterWorktree(name="{branch}") (or `git worktree add`). Do all work inside it.

Your job: run the COMPLETE weside build pipeline for {TICKET} by invoking the skill:
  Skill(skill="build")  with the ticket {TICKET}
Run it to a reviewable PR — Mode A or B, all quality gates, docs, PR, CI — UNCHANGED.
You own only this one Story. Do NOT merge the PR (Deliver is the human's job).

The Task* tools may be deferred — load them first via ToolSearch("select:TaskList,TaskUpdate")
if you need them. Claim your task with TaskUpdate(owner="builder-{TICKET}").

REPORTING IS NOT OPTIONAL: your plain-text output is INVISIBLE to the lead — you MUST call the
SendMessage tool. When the build reaches a reviewable PR (or hits its circuit breaker / a
blocker), send EXACTLY ONE structured message:
  SendMessage(to="team-lead", summary="builder-{TICKET} done|blocked",
              message="<state: PR #N created | blocked at <step> because <reason>>")
Even if you stop early, send the message first. Then mark your task completed via TaskUpdate.
```

### Step 7: Monitor + roll-up (Lead observes)

Builders report via the shared task-list and `SendMessage` (delivered automatically — do not
poll a terminal). Track per-builder state (dispatched → building → PR-ready / blocked).

**Idle ≠ done.** A builder running a full build idles repeatedly between turns; a contentless
`idle_notification` is NOT a completion signal and NOT a problem. Wait for the builder's actual
`SendMessage` — it can take minutes. Do not nudge on idle alone.

**State-as-truth (the robustness rule).** Never make "is this Story done" depend on a message
arriving. The source of truth is `orchestration.py story status {TICKET}` (checkpoints
`pr_created`/`ci_passed`) + the builder's branch. If a builder has been idle a long time with no
message, read its `story status` + branch directly to determine state, and nudge at most once.

When a builder is done/blocked (by message or by state), continue to Step 8 for that Story;
others keep running. Emit a running roll-up: `in-flight: {…} | PR-ready: {…} | blocked: {…}`.

### Step 8: Review each finished PR + record end

For each builder that reported a PR: the **Lead reviews** it (in the Companion review voice if
MCP-resolved, else the generic review lens) against the Story's ACs. This is the second human
gate — surface the review to the user; the Lead does **not** merge. The completion is already in
`orchestration.py` (the builder's `/we:build` wrote `pr_created`/`ci_passed`) — confirm it via
`story status {TICKET}` for the roll-up rather than writing it.

If a builder reported blocked, surface the blocker — do not silently retry.

### Step 9: Final roll-up + close the team

Emit the final roll-up (shipped-to-review / blocked / held-by-cap). Then:

```python
TeamDelete()
```

Always close the team, even on failure paths — a leaked team blocks the next run in this
session. If `TeamDelete` fails because a builder is still finishing, wait 30 s and retry twice,
then warn and continue.

---

## Rehearsal mode (`--rehearsal`)

Run the complete pipeline **without a real epic/story/code** — to shake out where the skills
stumble and optimise them. Repeatable via the built-in `/loop` skill
(`/loop /we:orchestrate FIXTURE --rehearsal`).

1. Set up a throwaway repo (or worktree) and copy the committed fixture template
   `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/references/fixture-story.md` into it as
   `docs/plans/FIXTURE-story.md`. Its AC is trivial but **real** (a pure `rehearsal_noop() -> 42`
   with a test) so the real review/test/PR steps have a genuine diff to chew on — a fully mocked
   no-op would short-circuit the skills and prove nothing.
2. Dispatch exactly one builder for the fixture, but instruct it: target a **throwaway worktree**,
   **plan-only ticketing** (no Jira transitions), and **no real PR** — create a draft on a scratch
   branch and delete it on teardown, or stop before push.
3. Run the **real** Step 1–8 build logic so genuine skill bugs surface.
4. Append the friction points (which step stumbled, the exact error) to a rehearsal log:
   `weside-core/docs/retros/YYYY-MM-DD-orchestrate-rehearsal.md`.
5. `TeamDelete`, delete the scratch worktree/branch. Loop to repeat.

This is the lab for the broader skill clean-up: each iteration → `plugin-dev:skill-reviewer` /
`plugin-validator` against the skill that stumbled → targeted fix → re-loop.

---

## Standalone fallback

No weside account / no MCP → the Lead reviews with the generic role lens, builders run normally
(builds never needed identity). Everything else is identical. The Agent-Teams env-flag is
required regardless of weside connection.

## Rules

- **Boot from state on every invocation** — reconstruct where the Epic stands from living files
  before anything else; never assume cached knowledge.
- **Dispatch only on an explicit confirm** — the ready set is shown first; the human gates it.
- **Hard cap ≤2 concurrent builders** — refuse and log any attempt to exceed it (runaway guard).
- **Builders run the full unmodified `/we:build`** — never reimplement or degrade the build/QA;
  a teammate spawns the build's own subagents (validated WA-1231: a builder ran `/we:build`
  through Step 5's parallel quality-gate subagents and wrote durable checkpoints).
- **Spawn builders with `Agent(team_name=…, name=…)`, all in one message** — never `Skill` for
  teammates. Builders live in their own watchable sessions.
- **Never inject Companion identity into builders** — user-scoped `select_companion` race; only
  the Lead carries a voice.
- **Lead reviews, never merges** — Deliver (merge, close ticket, move to Done) is the human's job.
- **Always `TeamDelete` on teardown** — even on failure paths.
- **Fail loud on the env-flag, degrade gracefully on identity** — same contract as `/we:council`.

## References

- `we/skills/council/SKILL.md` — the Agent-Teams machinery this skill mirrors
- `we/skills/build/SKILL.md` — the pipeline each builder runs unmodified
- `we/skills/epic/SKILL.md` — the boot-from-state / mirror pattern for "where we stand"
- `we/skills/map/SKILL.md` — plan-tree rendering across `docs/plans/`
- `we/skills/handoff/SKILL.md` — the durable cross-session bridge the Lead reads at boot
- `scripts/orchestration.py` — `story status|list|checkpoint|ready` (tracking + ready-set)
- `scripts/test_ready_set.py` — unit tests for the `compute_ready_set` pure helper
- `skills/orchestrate/references/fixture-story.md` — the rehearsal fixture template
- `weside-core/docs/plans/WA-1231-design.md` — full design, evidence, and the sibling program
- `weside-core/docs/retros/2026-06-04-orchestrate-rehearsal.md` — first rehearsal findings
