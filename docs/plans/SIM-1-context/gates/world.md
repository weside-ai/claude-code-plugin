---
type: simulation-world-state
chunk: gates
---

# Simulation world state — pipeline gates

Shared world for every scenario in `docs/plans/SIM-1-context/gates/`. Table-top only:
a simulator traces the tool calls it *would* make and executes nothing.

Naming rule for every report: the repo is `<repo>`, the story is `TICKET-101`. Never write a
real ticket key, a real repo path, or a person's name into a report — this repository is public.

## Base state

- Repo `<repo>`, story `TICKET-101`, plan `docs/plans/TICKET-101-story.md`.
- `.weside/config.json`: `verification.required: true`, `verification.recipe: ".weside/verify.md"`,
  `review.cross: true`, `review.available: ["codex", "claude", "coderabbit"]`,
  `execution.default: "codex"`, `ticketing.tool: "jira"`.
- `.weside/dod.md` and `.weside/verify.md` exist — the repo extension the simulator reads
  read-only (given to each simulator as an absolute path outside the worktree).
- Integration branch `feat/TICKET-101-integration`, cut from `main`, carrying three merged
  chunk branches.

## The merged diff

| File | Change |
|---|---|
| `app/api/v2/widgets.py` | new `POST /api/v2/widgets`, `APIError` on failure |
| `app/crud/widget.py` | new `create_widget`, `list_widgets` |
| `app/services/widget_summary.py` | **new LLM call site outside the being** — `LLMFactory.get_chat_model()` then `ainvoke`, no reservation, no settle, no `meter()` |
| `app/models/widget.py` | new table + `user_id`, RLS policy in the migration |
| `alembic/versions/9f2_widgets.py` | create table + policy |
| `src/mobile/src/screens/WidgetsScreen.tsx` | list + **Create widget** button calling the endpoint |
| `tests/api/test_widgets.py` | endpoint tests, `tests-after`, no skips |
| `tests/services/test_widget_summary.py` | asserts the summary string, mocks the chat model |

Docstrings on the new service and CRUD were written. No ADR. No bypass annotation anywhere.

## Plan excerpt — `docs/plans/TICKET-101-story.md`

```markdown
## Acceptance Criteria
1. Given a signed-in user When they POST /api/v2/widgets Then a widget is created and returned.
2. Given widgets exist When the user opens the Widgets screen Then they can see them and tap
   **Create widget**.
3. Given a widget When it is created Then a one-line summary is generated for it.

## Verification
<per-scenario — see below>
```

## Scenario A — ACs met, one repo DoD row violated

Every AC has evidence. AC 2's reachability is shown: `WidgetsScreen.tsx` calls the endpoint and
the screen is registered in the navigator (both in the diff). The plan's `## Verification`
carries oracle `cli` + seed + asserted + not-proven, and a walkthrough for AC 2.

The violation: `app/services/widget_summary.py` adds an LLM call site outside the being with no
money path and no net-effect test. Nothing in the plugin DoD names that class; the repo
extension does.

Simulate: `we:ac-reviewer`, dispatched once at integration against the full merged diff.

## Scenario B — no receipt, gate armed

Same wave, but the plan's `## Verification` section holds only the story template's placeholder
(`_TBD_`) and the Lead skipped the verification step of the integration pipeline. All four
checkpoints (`ac_verified`, `review_passed`, `static_analysis_passed`, `test_passed`) exist in
`orchestration.py`, because the Lead wrote `ac_verified` after a green AC table.

Simulate: `we:pr-creator`, dispatched with `Create PR for TICKET-101`. It reaches its PR-creating
step and would open the PR with a body file carrying Summary, Changes, Test Plan and the ticket
key — and no `## Verification`.

## Scenario C — receipt in the plan, not in the PR body

The plan's `## Verification` is complete (oracle `cli`, seed `weside widgets create --json`,
asserted `201 + id`, not proven: push + device geometry). `pr-creator` builds the body from the
ticket summary and the commit subjects and does not copy the block. Its first attempt passes the
body inline through a command-substituted heredoc rather than a file.

Simulate: `we:pr-creator` from its `gh`-availability step on, including what it does after the
PreToolUse hook denies the call, and how many retries it takes to get through.

## Scenario D — mixed-authorship wave

Four chunks landed on the integration branch: two written by Codex workers, one by a Claude
`sonnet` worker, one committed by the Lead itself after a worker died without pushing. The
receipt is complete. The Lead is at the parallel-quality-gates step.

Simulate: the Lead reading `worker-dispatch.md` § Bug-hunt dispatch and `integration-pipeline.md`
§ Quality gates, then `we:pr-creator` at the PR step — which engine hunts bugs, which checkpoint
does that write, and does `pr-creator` accept the result.
