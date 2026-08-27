<!-- markdownlint-disable -->

# Round 1 — Scenario (b): create mode, vague sentence, no ticketing

## Trace

0. **World state.** Session model: Opus. Mode: `acceptEdits`. cwd `/home/user/app` (branch
   `chore/cleanup`), main worktree `/home/user/app-main`. No `.weside/`, no `CONTEXT.md`, no
   `docs/plans/`. No TurboVault, no `superpowers`. graphify present. `gh` installed +
   authenticated.

### Prerequisites block

1. `Read("/home/fbiebl/weside/claude-code-plugin-SIM-1-p3/we/quality/dor.md")` — done.
2. `Read(".../we/references/verification.md")` — done.
3. `Read(".../we/references/long-running.md")` — done.
4. `Bash("git rev-parse --show-toplevel")` → `/home/user/app`.
   **Guessing point:** the skill says "resolve the repo root" for `.weside/dor.md`, but I am in a
   *feature worktree*. `git rev-parse --show-toplevel` returns the **worktree** root, not the main
   clone. Since `.weside/` is committed content, both would carry it — but Step 6.1 explicitly
   distinguishes worktree-cwd from main-worktree, and this line does not. I used the worktree root.
5. `Bash("test -f /home/user/app/.weside/dor.md")` → absent. Silently proceed on plugin DoR only. OK.
6. Model check: session is Opus → nothing said. `[UNPROMPTED-adjacent]` — I would not have
   downgraded myself anyway; the line only pays off on a non-Opus session.
7. `Bash("test -d /home/user/app/.weside")` → absent.
   → Emit once: *"No `.weside/` here — consider `/we:setup` first. Continuing in degraded
   (Plan-only) mode."*
   **First contradiction noticed and parked:** the skill equates "no `.weside/`" with
   "no ticketing → Plan-only". But `.weside/` absence says nothing about ticketing, and
   `references/ticketing.md` rank 3 is `gh` CLI, which *is* available here. See Defect D1.

### Ticketing detection (Create Mode step 3 needs it, so I did it early)

8. `Bash("command -v gh && gh auth status")` → authenticated.
9. Check for weside MCP `execute_tool` / Atlassian `jira_*` in the tool list → neither present.
10. `Bash("gh issue list --limit 1")` → exits 0, repo has Issues enabled.
    → **Detected ticketing = GitHub Issues (rank 3), NOT Plan-only.** The scenario brief calls this
    "no ticketing"; the skill's own reference calls it ticketing. I followed the reference.

    **The branch I therefore did not play — Plan-only (`ticketing.md` rank 4).** Naming what
    breaks there, since detection routed me away from it:
    - `{TICKET}` has no definition **at all**, so `docs/plans/{TICKET}-story.md` has no filename
      and neither does the frontmatter `story:` key — D2's third bullet is the only escape, and
      the skill does not offer it.
    - Step 6.2's live arm inverts: "If ticket exists" is false and "If no ticket → create minimal
      ticket first" is unexecutable, so **6.2 has no executable arm** in Plan-only mode. That
      sharpens D5 — the step is not merely double-booked, it is empty on one of its two branches.
    - 6.3's commit message `"docs: add {TICKET} plan — {Story Title}"` has no key to interpolate.
    - Downstream, orchestrate Step 0 resolves its target from a key the user has no way to type,
      because nothing ever printed one.

### Vision alignment + Training on the Job

11. `Bash("test -f /home/user/app/.weside/vision.md")` → absent.
12. weside MCP not connected → Level 3 unavailable. → **Level 1: skip vision checks.**
13. Emit the Training-on-the-Job hint verbatim:
    > "Would you like to define a project vision? It helps me check stories against your product
    > goals. Run `/we:setup vision` to get started — or we continue without."
    `[USER]` *"nah later"*
    → skill says "never ask again". **There is nowhere to persist that** — `.weside/` does not
    exist, and the skill names no store. Defect D8.

### Create Mode — step 1: design session (grill-style, one question at a time)

Requirements are vague ("make onboarding less painful"), so per Refine Step 2 I brainstorm first.
`superpowers` absent → the three targeted fallback questions.

14. Ask Q1 (with my recommendation attached): *"What does 'painful' look like concretely — is it
    signup friction, or what happens after signup? My guess: the post-signup moment."*
    `[USER]` *"after signup i think"*
15. Ask Q2: *"What are you actually trying to enable — a faster path to first value, or fewer
    support questions? Recommendation: first value."*
    `[USER]` *"both but mostly the first one"*
16. Ask Q3: *"What's the simplest version — a tooltip pass, or a real first-run flow?"*
    `[USER]` *"honestly the problem is you sign up and land on an empty companion list and have no
    idea what to do. i want a guided first run — pick a starter, see it work."*
    → intent established. **Only now do I scope ACs** (as the skill demands).
17. Follow-ups, still one at a time:
    - *"Should the starter set come from the backend so you can tune it without a store build?
      Recommendation: yes, a seed endpoint."* `[USER]` *"yes"*
    - *"Does the flow re-appear after reinstall? Recommendation: device-local flag, so yes."*
      `[USER]` *"fine"*
18. Glossary offer: skill says *"offer to record it in the project glossary (`CONTEXT.md`)"*.
    `CONTEXT.md` does not exist. The skill gives no branch for "no glossary yet" —
    I improvised: offered to *create* `CONTEXT.md` with `first run` / `starter companion`.
    `[USER]` *"skip"*. Defect D9.

### Create Mode — step 2: scope check

19. Judgement, no tool call: three phases of **one coherent change** (backend seed → mobile screen →
    persisted flag), not many independent slices → **stays a single Story**, not `/we:epic`.
    Skill line 99 ("the urge to split into phases is the orchestrate signal") is what decided it.

### Create Mode — step 3: create the ticket

20. **Blocked on an undefined value.** The skill's whole output contract is keyed on `{TICKET}`
    and never says what `{TICKET}` is when ticketing is GitHub Issues (an integer) or absent
    (nothing). See Defect D2 — this is the round's headline defect.
    Improvised: create the issue, then coin `GH-<n>` for the filename.
21. `Bash("gh issue create --title 'First-run guided onboarding for new users' --body-file /tmp/issue.md")`
    with the DoR minimal template:
    ```markdown
    ## User Story
    As a new user I want a guided first run so that I reach a working companion
    without guessing what to do.

    ## Plan
    Implementation Plan: docs/plans/GH-7-story.md
    ```
    → `https://github.com/acme/app/issues/7`. So `{TICKET}` := **`GH-7`** (my invention).
22. Create Mode step 4 "Link to Epic (if applicable)" → GitHub Issues have no epic link and no
    parent field. `ticketing.md` covers this silence only for *transitions*, not for epic linking.
    I skipped it and left `epic:` out of the frontmatter. Defect D10.

### Create Mode — step 5: "continue as Refine Mode (Steps 4-6)"

**Step 4 — Create Plan (EnterPlanMode)**

23. `EnterPlanMode()`
24. `Bash("test -f /home/user/app/CONTEXT.md")` → absent → no glossary vocabulary to honour.
25. TurboVault unavailable → emit once, verbatim:
    > "⚠️ TurboVault unavailable — using grep fallback; architecture context may be incomplete.
    > Check the MCP config."
26. `Glob(pattern="docs/architecture/**/*.md")` → **0 hits** (this repo has no `docs/` at all).
27. `Grep(pattern="onboarding", include="*.md", path="docs/")` → **path does not exist, tool errors.**
    Improvised: `Grep(pattern="onboarding|first.run|welcome", include="*.md", path=".")`
    → hits only `README.md`. The skill's fallback hard-codes `path="docs/"` with no
    "if it exists" guard. Defect D11.
28. `Read("/home/user/app/README.md")` — stack confirmation only.
29. `Bash("python3 scripts/graphify/check.py --build-if-missing")` → builds (~30 s).
    Note: relative path, run from the *feature worktree* cwd. It happened to work here.
30. `Bash("python3 scripts/graphify/query.py 'UserRouter CompanionListScreen AsyncStorage onboarding_seen' --top 10")`
    → names `app/api/routes/companions.py`, `app/api/routes/users.py`, `app/schemas/user.py`,
    `src/screens/CompanionListScreen.tsx`, `src/navigation/RootNavigator.tsx`, `src/lib/storage.ts`.
    These feed the per-phase `**Files:**` lists.
    **Guessing point:** the skill says use "identifier-style terms, not prose" but I had no
    identifiers before this — I had to grep/glob first to *find* identifiers to feed the graph.
    The ordering in the skill is backwards for a greenfield story.
31. `Glob("src/screens/*.tsx")`, `Read("src/screens/CompanionListScreen.tsx")`,
    `Read("src/navigation/RootNavigator.tsx")`, `Read("app/api/routes/users.py")`,
    `Read("src/lib/storage.ts")` — five reads to ground the Files lists.
    `[UNPROMPTED]` — line 161 ("Read the plan and the files it names in full") told me to read a
    plan that does not exist yet; I read the *code* instead, which nothing told me to do at this
    granularity. Defect D12.
32. Verification recipe: `Bash("test -f /home/user/app/.weside/verify.md")` → absent.
    `verification.md` says *"Missing recipe file → do not silently skip. Say once that the repo has
    no recipe … and propose adding `.weside/verify.md` in the same PR."*
    **The SKILL never surfaces this obligation** — only the reference does, and the plan template's
    Verification block has no slot for it. I improvised: said it once, and added a line to the plan's
    Verification section. Defect D13.
33. `ExitPlanMode(plan=<the markdown below>)`

**Step 5 — approval**

34. `[USER]` *"yep go"* → approval.

**Step 6 — the six commands**

35. **6.1 Save plan.** The skill says *"Read approved plan from `~/.claude/plans/{codename}.md`"*.
    `{codename}` is defined **nowhere** in the skill, in `plan-format.md`, or in the references.
    Improvised: I already hold the plan text in context, so I skipped the read entirely.
    Defect D3.
    Resolve the main worktree — Step 6.1 describes it in prose ("usually the original clone,
    e.g. `~/<workspace>/<repo>/`") while Step 6.3 gives an exact recipe. I used 6.3's recipe early:
    `Bash("git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\\/heads\\/main$/{print p; exit}'")`
    → `/home/user/app-main`. Defect D4.
    `Bash("mkdir -p /home/user/app-main/docs/plans")` `[UNPROMPTED]` — nothing says the directory
    may not exist; `Write` would create it, but I checked.
    `Write("/home/user/app-main/docs/plans/GH-7-story.md", <plan with status: approved>)`
36. **6.2 Update ticket.** *"If no ticket → create minimal ticket first, then save plan with ticket
    number."* — I already created it at Create-Mode step 3. The two lists disagree about who owns
    ticket creation; on a literal reading of 6.2 after Create-Mode step 3 I would have opened a
    **second** issue. Defect D5. What I actually did: nothing — the body already carries the plan
    link. So 6.2 was a no-op in this scenario.
37. **6.3 Commit plan to main.**
    ```bash
    MAIN_WORKTREE=$(git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p; exit}')
    cd "$MAIN_WORKTREE" && \
    [ "$(git branch --show-current)" = "main" ] && \
    git add docs/plans/GH-7-story.md && \
    git commit -m "docs: add GH-7 plan — First-run guided onboarding" && \
    git push || echo "WARN: main worktree not on main branch — plan saved but not committed. Commit manually."
    ```
    Executable here. But I **stopped and asked** before running it, because it pushes to `main`
    unprompted. Defect D6.
38. **6.4 Checkpoint.**
    `Bash("python3 /home/fbiebl/weside/claude-code-plugin-SIM-1-p3/we/scripts/orchestration.py story checkpoint GH-7 refined")`
    → executes; `story_key` is a free string in the sqlite schema, so `GH-7` is accepted.
    This is the one of the six that works verbatim.
39. **6.5 Vault links.** TurboVault absent → skipped silently, as instructed. A no-op line.
40. **6.6 Output.** Execution-surface heuristic: 3 real phases, coherent multi-layer change →
    dispatch. `parallel_groups: []` (phases 2 and 3 share `RootNavigator.tsx`).
    Long-running: I judged this **one sitting** → no `/loop` line printed. The skill gives no
    criterion for "spans more than one sitting". Defect D14.
    Emitted:
    ```
    Plan saved to docs/plans/GH-7-story.md. /we:story DONE.

    Recommended next: /we:orchestrate GH-7   ← 3 phases, sequential (phases 2+3 share the navigator), coherent backend→mobile change
    (or /we:orchestrate GH-7 --solo if you'd rather run it inline.)
    ```
41. **STOP.** No branch, no code, no auto-continue.

---

## The plan I would have written

**Path:** `/home/user/app-main/docs/plans/GH-7-story.md`
(main worktree, per Step 6.1 — *not* `/home/user/app/docs/plans/`, which is the `chore/cleanup`
feature worktree I am standing in.)

```markdown
---
type: story-plan
story: GH-7
created: 2026-08-27
status: approved
parallel_groups: []
---

# Plan: First-run guided onboarding for new users

## Context

A new user signs up, lands on the companion list, and it is empty — there is no starter,
no prompt, no next step, and the app gives no hint that creating a companion is the thing
to do. That blank screen is the actual pain behind "onboarding is painful"; signup itself
is fine. What the user cares about most is time-to-first-value: pick something, see it
respond, understand what the app is for. The starter set has to come from the backend so
it can be tuned without shipping a store build — that constraint came out of the design
session and rules out a hard-coded list in the bundle. The "already seen this" flag is
device-local on purpose: a reinstall re-shows the flow, which the user accepted as the
cheaper trade against a server round-trip on cold start. There is no `.weside/` config,
no architecture docs and no glossary in this repo yet, so this plan carries its own
vocabulary: *first run* = the guided flow, *starter companion* = a backend-suggested
seed entry.

## Acceptance Criteria
1. **Given** a signed-in user who has never completed the first run **When** the app opens
   the companion list **Then** the first-run screen is presented over it instead of an empty list.
2. **Given** the first-run screen is open **When** the user taps a starter companion card
   **Then** that companion is created for them and the app navigates to it.
3. **Given** the user has completed or dismissed the first run **When** they cold-start the app
   again **Then** the first-run screen is not shown and the companion list renders normally.
4. **Given** the starter endpoint is unreachable **When** the first-run screen loads
   **Then** it shows a retry affordance and a "skip for now" action, never a blank screen.

## User Journey
> **This story is only DONE when the user can experience the journey end-to-end.**

1. A brand-new account opens the app and reaches the companion list route.
2. The first-run screen appears with three starter companions and a "skip for now" link.
3. The user taps one; it is created and opened, ready to talk to.
4. The flag is persisted; the next cold start goes straight to the list.

## Testing Requirements
- Unit: the starter-suggestion service (shape, ordering, empty-set behaviour); the
  first-run gate hook (seen / not-seen / storage-throws).
- Integration: `GET` starters + create-from-starter against the FastAPI test client,
  including the unauthenticated and empty-catalogue cases.
- Component: the first-run screen renders cards, the tap path calls create-then-navigate,
  the error path renders retry + skip.
- Edge cases: storage read throws (treat as not-seen); user already owns companions
  (never show first run); double-tap on a card creates exactly one companion.

## Verification
> How this will be observed running — not inferred from green tests.

- **Oracle:** ui — AC 1–3 are all "the user sees / taps / reaches"; reachability is not
  provable from an endpoint. Oracle 1 (cli) covers the backend half and runs first.
- **Seed:** `uvicorn app.main:app --reload` + a fresh account, then
  `curl -s localhost:8000/api/v1/onboarding/starters -H "Authorization: Bearer $TOKEN"`
  for the backend half; `npx expo start --web` and a cleared AsyncStorage for the UI half.
- **Assert:** endpoint returns 200 with a non-empty `starters[]` each carrying `id`/`name`;
  in the app, route `/companions` shows the node labelled "Choose a starter", tapping the
  first card lands on the companion detail route, and a reload keeps the list (no re-show).
- **Not provable here:** native cold-start behaviour on a real device (Expo Web is the
  local surface) and the reinstall path — owed by a manual device round before release.
- **Missing CLI verb:** there is no project verb that resets a user to "never onboarded".
  Ships with this story as `python -m app.cli reset-onboarding <email>` — the seed above
  otherwise needs a hand-written SQL dance.
- **No `.weside/verify.md` in this repo** — proposed in the same PR.

## Technical Approach
**Patterns:** FastAPI router + Pydantic response schema under the existing
`app/api/routes/` layout; suggestions read from a config-backed catalogue, not hard-coded
in the route body. Mobile: an existing-navigator gate (a conditional route in
`RootNavigator`), not a new navigator; storage through the existing `src/lib/storage.ts`
wrapper rather than importing AsyncStorage directly. No architecture docs or ADRs exist
in this repo to reference — this plan is the first written record.

## Implementation Phases

### Phase 1: Backend starter catalogue + endpoint
- **Goal:** an authenticated client can fetch a tunable list of starter companions and
  create one from it.
- **Files:** `app/api/routes/onboarding.py` (new), `app/schemas/onboarding.py` (new),
  `app/services/starters.py` (new), `app/api/routes/__init__.py`,
  `app/cli.py` (the `reset-onboarding` verb), `tests/api/test_onboarding.py` (new)
- **Approach:** `GET /api/v1/onboarding/starters` returns the catalogue;
  `POST /api/v1/onboarding/starters/{id}` creates the companion for the caller and returns
  it. Catalogue lives in config so it is tunable without a deploy of the mobile app.

### Phase 2: Mobile first-run screen
- **Goal:** a screen that lists starters, creates one on tap, and handles the error path.
- **Files:** `src/screens/FirstRunScreen.tsx` (new), `src/api/onboarding.ts` (new),
  `src/navigation/RootNavigator.tsx`, `__tests__/FirstRunScreen.test.tsx` (new)
- **Approach:** fetch starters on mount; card tap calls the create endpoint then navigates
  to the companion detail route; failure renders retry + "skip for now".

### Phase 3: Persisted first-run flag + gate
- **Goal:** the flow shows exactly once per install and never blocks a returning user.
- **Files:** `src/lib/storage.ts`, `src/hooks/useFirstRun.ts` (new),
  `src/navigation/RootNavigator.tsx`, `src/screens/CompanionListScreen.tsx`,
  `__tests__/useFirstRun.test.ts` (new)
- **Approach:** `useFirstRun()` reads the persisted flag (a storage throw counts as
  not-seen); the navigator gates the first-run route on it; completing or skipping writes
  the flag. A user who already owns companions is treated as seen.

> Phases are sequential. 2 and 3 both edit `src/navigation/RootNavigator.tsx`, so they are
> not disjoint — `parallel_groups: []`. Phase 2 also consumes Phase 1's endpoint shape.

## Design Decisions

| Decision | Alternatives Considered | Why This |
|---|---|---|
| Starter catalogue served by the backend | Hard-coded list in the app bundle | Tunable without a store build — the user's explicit constraint |
| Device-local "seen" flag | Server-side `onboarding_completed` on the user row | No cold-start round-trip; user accepted that reinstall re-shows the flow |
| Gate inside the existing RootNavigator | A separate onboarding navigator | Three phases of work, not a navigation rewrite; keeps the diff reviewable |
| A guided first-run flow | A tooltip/coach-mark pass over the existing list | The pain is "nothing to look at", not "I can't find the button" |
| Ship `reset-onboarding` CLI verb | Document a SQL snippet in the PR | Transcripts rot, verbs compound (`references/verification.md`) |

## Code Guidance
**DO:** put the catalogue behind a service so the route body stays thin; go through
`src/lib/storage.ts`; treat a storage read failure as "not seen"; keep the skip action
reachable on every state of the screen including the error state.
**DON'T:** import AsyncStorage directly in a screen; hard-code the starter list in the
mobile bundle; block app boot on the starters fetch; add a second navigator.

## Security Review Required
No — the endpoints are authenticated reads and a create scoped to the calling user, no new
data class, no new trust boundary. Confirm the create path derives the owner from the token
and never from the request body.

## Documentation Impact
- **Docstrings** — `app/services/starters.py` carries why the catalogue is config-backed;
  `useFirstRun` carries the storage-throws-means-not-seen rule.
- **Architecture doc** — none; no cross-module interplay changes.
- **ADR** — none; both decisions are cheap to reverse.
- **Generated** — OpenAPI schema regenerates with the new router.
- **New doc** — `.weside/verify.md`, because the repo has no verification recipe at all and
  code cannot carry "how DEV comes up here".
```

---

## Conformance checklist

| Skill instruction | Followed? | Note |
|---|---|---|
| Read the 3 prerequisite files | yes | dor / verification / long-running |
| Repo-local `.weside/dor.md` additive check | yes | absent → silent proceed |
| "Run this on Opus" | n/a | already Opus; no output |
| Suggest `/we:setup` when `.weside/` absent, do not block | yes | said once |
| Ticketing detection per `references/ticketing.md` | yes | landed on `gh` (rank 3), **not** Plan-only |
| Ticket MINIMAL (DoR template) | yes | user story + plan link, nothing else |
| Create Mode 1 — design session | yes | grill-style, one question at a time, recommendation attached |
| Brainstorm first when vague | yes | but reached by inference — Create Mode never points at it (D7) |
| `superpowers` brainstorming skill | n/a | not installed → three targeted questions |
| Create Mode 2 — scope check | yes | coherent phased change → one Story, not an Epic |
| Create Mode 3 — create ticket | yes | `gh issue create` → #7 |
| Create Mode 4 — link to Epic | **no** | GitHub Issues has no parent field; skill gives no branch (D10) |
| Glossary offer on resolved term | partial | `CONTEXT.md` does not exist; improvised a create-offer (D9) |
| Step 4 — `EnterPlanMode` | yes | |
| TurboVault unavailable → say the warning verbatim | yes | |
| grep fallback `path="docs/"` | **no** | path does not exist; widened to `.` (D11) |
| graphify blast radius | yes | check.py + query.py both ran |
| Session Context → Plan (narrative Context + Design Decisions) | yes | 5 decision rows, all from the session |
| "Read the plan and the files it names in full" | **no** | no plan exists at that point (D12) |
| Plan template sections | yes | all 12 sections present incl. Verification |
| Phase headers `^### Phase (\d+): (.+)$` | yes | 3 phases |
| `parallel_groups` filled from disjointness | yes | `[]`, with the reason written under the phases |
| `epic:` frontmatter | omitted | standalone story, no epic — permitted |
| Step 5 — `ExitPlanMode` | yes | |
| 6.1 save to main worktree | yes | `/home/user/app-main/docs/plans/GH-7-story.md` |
| 6.1 read from `~/.claude/plans/{codename}.md` | **no** | `{codename}` undefined (D3) |
| 6.2 update ticket | no-op | already done at Create-Mode 3 (D5) |
| 6.3 commit + push to main | **gated** | asked first — unprompted push to protected main (D6) |
| 6.4 checkpoint | yes | only one of the six that runs verbatim |
| 6.5 vault links | skipped silently | correct |
| 6.6 output + surface recommendation | yes | dispatch, 3 phases, sequential |
| 6.6 long-running invocation | not printed | judged one sitting; criterion undefined (D14) |
| STOP after 6 | yes | |
| Vision Alignment Level 1 | yes | skipped checks |
| Training on the Job hint | yes | but "never ask again" has no store (D8) |

---

## Defects

### D1 — "no `.weside/` ⇒ no ticketing ⇒ Plan-only" is a false chain — **friction**

> `we/skills/story/SKILL.md:34` — "**Verify setup:** if `.weside/` doesn't exist in the project,
> suggest the user run `/we:setup` first to verify prerequisites (`gh` CLI, Jira access,
> recommended plugins). Do NOT block — `/we:story` can proceed in degraded modes (no ticketing →
> Plan-only)."

The parenthetical welds two unrelated facts together. `.weside/` absence is a *config* fact;
ticketing availability is a *tool* fact resolved by `references/ticketing.md`. In this world
`.weside/` is absent **and** `gh` works, so I am simultaneously in "degraded mode" and in full
GitHub-Issues ticketing. A less careful reader takes the parenthetical as the ruling and skips
ticket creation entirely — which loses `{TICKET}` and therefore the plan filename.

**Smallest fix:** cut the parenthetical to `Do NOT block.` and add one line:
`Ticketing availability is decided by references/ticketing.md, independently of .weside/.`

### D2 — `{TICKET}` is undefined outside a Jira-shaped world — **blocking**

> `SKILL.md:43` — "| **Plan** | `docs/plans/{TICKET}-story.md` | …"
> `SKILL.md:262` — "If no ticket → create minimal ticket first, then save plan with ticket number."
> `we/references/ticketing.md:8` — "4. **None** → Plan-only mode (no ticket, just `docs/plans/`)"

Every artifact in the pipeline is keyed on `{TICKET}` — the filename, the frontmatter `story:`,
the checkpoint key, orchestrate's `docs/plans/{KEY}-story.md` lookup and its
`git branch --list 'feat/{KEY}-*'`. Nothing anywhere says what `{TICKET}` is when the ticketing
tool is GitHub Issues (a bare integer) or absent (nothing at all). `ticketing.md` says "Plan-only
mode (no ticket, just `docs/plans/`)" and stops — it does not name the file.

Every available choice breaks something:
- `7` → `docs/plans/7-story.md`; frontmatter `story: 7` parses as an int; `feat/7-*` branches.
- `GH-7` (what I picked) → readable file, but the user then types `/we:orchestrate GH-7` and
  orchestrate Step 1's "every ticket **with comments**" resolves `gh issue view GH-7` → fails.
- a slug (`first-run-onboarding`) → readable and stable, but no ticket linkage at all.

**Smallest fix:** one line in `ticketing.md` and one in the SKILL's Output table:
`{TICKET} := the Jira/Linear key; for GitHub Issues gh-<number> (lowercase, and skills strip the
gh- prefix before any gh call); in Plan-only mode a kebab-case slug of the story title.`

### D3 — `{codename}` is defined nowhere — **blocking**

> `SKILL.md:261` — "1. **Save plan:** Read approved plan from `~/.claude/plans/{codename}.md`."

`{codename}` appears exactly once in the skill and once in the repo. It is not in `plan-format.md`,
not in the frontmatter spec, not produced by any earlier step. A session that dutifully tries to
execute 6.1 has to `ls ~/.claude/plans/` and guess by mtime. I skipped the read because I hold
the plan text in context — which is what any session does, making the whole instruction a no-op
with a broken path in it.

**Smallest fix:** replace with `1. **Save plan:** take the plan you just had approved…`.

### D4 — main-worktree resolution is specified twice, differently — **friction**

> `SKILL.md:261` — "**in the project's main worktree** (the directory where `main` is checked out —
> usually the original clone, e.g. `~/<workspace>/<repo>/`)"
> `SKILL.md:263` — "Resolve `MAIN_WORKTREE=$(git worktree list --porcelain | awk …)`"

6.1 is prose-and-a-guess, 6.3 is an exact command. They are the same lookup two steps apart, and
6.1 runs first — so the step that must not guess is the one told to guess. In this scenario the
prose heuristic ("the original clone") would have pointed at `/home/user/app`, the *feature*
worktree, because that is the plainer-looking path; only 6.3's recipe finds `/home/user/app-main`.

**Smallest fix:** move the `MAIN_WORKTREE=…` resolution to the top of Step 6 as step 6.0 and have
both 6.1 and 6.3 reference `$MAIN_WORKTREE`.

### D5 — Create Mode and Step 6.2 both claim ticket creation — **blocking**

> `SKILL.md:332` (Create Mode) — "3. Create ticket via ticketing tool (minimal)"
> `SKILL.md:334` — "5. Continue as Refine Mode (Steps 4-6)"
> `SKILL.md:262` (Step 6.2) — "**Update ticket:** If ticket exists → update description with plan
> link. If no ticket → create minimal ticket first, then save plan with ticket number."

Create Mode routes into Steps 4–6, and 6.2 re-runs ticket creation. Followed literally in CREATE
mode you open the issue twice. Worse, 6.2's fallback ("create ticket first, *then* save plan with
ticket number") describes an ordering that 6.1 has already violated — 6.1 wrote
`docs/plans/{TICKET}-story.md` one step earlier, which is impossible without the number. So 6.1
and 6.2 are mutually unsatisfiable whenever the no-ticket branch of 6.2 is live.

Related: Create Mode skips Refine **Step 3** (Update Ticket MINIMAL) by jumping to 4–6, so the
ticket *template* lives in a step Create Mode never visits; I had to reach back into Step 3 (and
`dor.md`) to know what to put in the issue body.

**Smallest fix:** make Create Mode "3. Create ticket via ticketing tool — body per Step 3's
template" and reduce 6.2 to `**Update ticket:** ensure the description links the plan.` Delete
the no-ticket branch, which by then cannot fire.

### D6 — Step 6.3 pushes to `main` with no confirmation, and lies when it half-fails — **blocking**

> `SKILL.md:264-269` — "`cd "$MAIN_WORKTREE" && [ … ] && git add … && git commit … && git push ||
> echo "WARN: main worktree not on main branch — plan saved but not committed. Commit manually."`"

Two problems in one chain.

1. **Unconfirmed push to a protected branch.** The chain commits *and pushes* to `main` as a
   post-approval automatic step. The user approved a *plan*, not a push. In any repo with branch
   protection this fails; in one without, it is an unreviewed direct-to-main push the user never
   sanctioned.
2. **The `||` arm mislabels three different failures as one.** `A && B && C && D || E` fires `E`
   if *any* of B/C/D fails. If `git commit` succeeds and `git push` is rejected, the user is told
   "plan saved but **not committed** — commit manually", which is false: it *is* committed, and
   the real problem is the push. If `MAIN_WORKTREE` is empty (no worktree on `main` — an entirely
   normal state), `cd ""` silently succeeds into `$HOME` and the `git` commands then run against
   whatever repo, if any, lives there.

**Smallest fix:** split it — `git add && git commit` unconditionally, then print the push as a
suggested command instead of running it; guard with `[ -n "$MAIN_WORKTREE" ] || { echo …; exit 1; }`;
and make the failure message name the step that failed.

### D7 — Create Mode's step 1 is a one-liner where the whole vague-input protocol lives elsewhere — **friction**

> `SKILL.md:330` — "1. Design session — ask clarifying questions"
> vs `SKILL.md:93` (Refine Step 2) — "**Brainstorming first if requirements are vague.** … If not,
> use targeted questions: … Only scope ACs once you understand the user's actual goal."

CREATE mode is *the* mode whose input is a vague sentence — that is its trigger shape
(`/we:story "Feature description"`). Yet its instruction is four words, and the actual protocol
(brainstorm before scoping, one question at a time with a recommendation, glossary capture,
`superpowers` fallback) sits in REFINE Step 2, which Create Mode's numbered list never cites.
Create Mode cites Refine Step 2 exactly once, in item 2, and only for the scope check. I applied
the Step 2 protocol because I had read the whole file top to bottom; a session that jumped to the
Create Mode section would have written ACs off "make onboarding less painful".

**Smallest fix:** item 1 becomes
`1. Design session — run Refine Mode Step 2 (brainstorm-first, one question at a time).`

### D8 — "never ask again" has no store — **friction**

> `SKILL.md:375` — "One-time hint. If user says no → never ask again."

There is no state anywhere to record the refusal. In this world `.weside/` does not exist, so
there is not even a config file to write it into, and the skill names no key. Every future
`/we:story` in this repo re-asks. The instruction is unimplementable as written.

**Smallest fix:** name the store — `write hints.vision_declined: true into .weside/config.json
(creating it if absent); skip the hint when that key is true.`

### D9 — glossary capture assumes `CONTEXT.md` already exists — **friction**

> `SKILL.md:91` — "When a fuzzy or conflicting term gets resolved, offer to record it in the
> project glossary (`CONTEXT.md`, see `/we:grill`)."
> `SKILL.md:119` — "**Glossary:** If `CONTEXT.md` exists at the repo root, read it and use its
> canonical vocabulary"

Line 119 has the exists-guard; line 91 does not. Resolving "onboarding" → "first run" is exactly
the case line 91 is written for, and there is no file to record it in. Also unstated: *which*
repo root — I am in a feature worktree.

**Smallest fix:** line 91 → "…offer to record it in the project glossary (`CONTEXT.md` — offer to
create it if absent)".

### D10 — "Link to Epic (if applicable)" has no ticketing-tool branch — **friction**

> `SKILL.md:333` — "4. Link to Epic (if applicable)"

GitHub Issues has no parent/epic field. `ticketing.md` explicitly handles the analogous gap for
*transitions* ("GitHub Issues (no status transitions) / no ticketing tool → skip silently") but
says nothing about linking, so this step dead-ends. `dor.md` compounds it: "**Ticket linked** —
Connected to parent Epic (if using ticketing tool)" is a *Required (Blocking)* DoR row, and I am
"using a ticketing tool". Read strictly, my story fails DoR for a reason no action can satisfy.

**Smallest fix:** "4. Link to Epic (if applicable **and the ticketing tool supports parents** —
GitHub Issues does not; record the epic in the plan's `epic:` frontmatter instead)." And soften
the DoR row the same way.

### D11 — the grep fallback hard-codes a path that need not exist — **friction**

> `SKILL.md:132-133` — "`Grep(pattern="<topic keyword>", include="*.md", path="docs/")` /
> `Glob(pattern="docs/architecture/**/*.md")`"

This repo has no `docs/` at all. The `Grep` call errors on a missing path (the `Glob` merely
returns empty, which is fine). The fallback is the *degraded* branch — it is the one most likely
to run in a repo that has no docs infrastructure, i.e. exactly the repo where `docs/` is absent.

**Smallest fix:** drop `path="docs/"` (search the repo) or prefix with
`if docs/ exists —`.

### D12 — "Read the plan and the files it names in full" is in the wrong skill — **no-op**

> `SKILL.md:161` — "**Read the plan and the files it names in full.** A partially-read plan
> produces a partially-built story, and the sections you skip are the ones carrying the
> constraint."

This sits inside Step 4 (*Create* Plan). At that moment no plan exists — I am about to write one.
The paragraph is worker/orchestrate guidance ("a partially-read plan produces a partially-built
story") that has drifted into the plan-*writing* skill. Its second half ("Load more files than
feel necessary") is good advice for Step 4, but the first half instructs an impossible read.

**Smallest fix:** cut the first sentence; keep "Load more files than feel necessary — a wrong
assumption costs more than a wide read."

### D13 — the no-`.weside/verify.md` obligation never reaches the SKILL — **friction**

> `we/references/verification.md:85-87` — "Missing recipe file → do not silently skip. Say once
> that the repo has no recipe, verify with what the stack offers …, and propose adding
> `.weside/verify.md` in the same PR."
> `SKILL.md:200-201` — "See `references/verification.md`; commands live in `<repo>/.weside/verify.md`."

The SKILL points at `.weside/verify.md` as though it exists and gives no branch for its absence.
The obligation is real (say it once, propose the file in the same PR) but lives only in the
reference, and the plan template has no slot for it — I had to invent one under
*Documentation Impact* / *Verification*. In a repo with no `.weside/` at all — the exact repo the
SKILL's own line 34 anticipates — this fires every time.

**Smallest fix:** SKILL line 201 → "…commands live in `<repo>/.weside/verify.md`; absent → say so
once and propose it under Documentation Impact."

### D14 — "spans more than one sitting" is an unjudgeable trigger — **friction**

> `SKILL.md:282-283` — "**When the work spans more than one sitting, print the long-running
> invocation too**"

Three phases, one PR, a day's work. Is that one sitting? The skill gives no test and
`long-running.md` gives none either — it says what a plan *owes* before unattended work is
legitimate (state file, scriptable verification, written exit criterion, releasable main) but
never says when the trigger fires. Two sessions on the same plan will disagree, and the cost of
disagreeing is asymmetric: printing an unnecessary `/loop` line is harmless, omitting a needed
one loses the mechanic entirely.

**Smallest fix:** make it structural — "print it when the plan has 4+ phases or a non-empty
`depends_on`, or when the user says they will be away."

### D15 — the plan template and `docs/plan-format.md` disagree — **blocking**

> `SKILL.md:164-171` frontmatter carries `type: story-plan` and `epic: {EPIC-SLUG-OR-KEY}`;
> `SKILL.md:198` adds a `## Verification` section.
> `docs/plan-format.md:19-33` — the frontmatter table lists **only** `story`, `created`, `status`,
> `parallel_groups`, and `docs/plan-format.md:124-183` "Full Template" has **no** `## Verification`,
> and its frontmatter block has no `type:` and no `epic:`.

`plan-format.md` opens by declaring itself the contract — "This document specifies the exact
format both sides depend on. Changes here are versioned" — and then does not describe the format
the producing skill actually emits. `epic:` is the worse half: `SKILL.md:390` calls it
load-bearing ("a missing `epic:` makes the story invisible to orchestration") while the
authoritative format spec does not list it at all. Anything validating a plan against
`plan-format.md` rejects a correct plan, and anything generating from `plan-format.md` produces
one orchestrate cannot place.

**Smallest fix:** add `type`, `epic` and the `## Verification` section to `plan-format.md`'s
frontmatter table and Full Template, and bump its changelog.

### D16 — `status: approved, story: {TICKET}` is not YAML — **no-op**

> `SKILL.md:261` — "Update frontmatter to `status: approved, story: {TICKET}`."

Written as one inline mapping it is invalid in the block frontmatter it describes. Obvious to a
reader, but it is the kind of literal a headless worker copies.

**Smallest fix:** "set `status: approved` and `story: {TICKET}` in the frontmatter."

---

## What I needed and did not find

- **A definition of `{TICKET}` for non-Jira worlds.** The single most load-bearing token in the
  whole skill and the one thing no file defines. (D2)
- **A Create-Mode ticket-body template.** Create Mode says "create ticket (minimal)" and routes to
  Steps 4–6, skipping Step 3 where the template lives. I reached back for it; the skill did not
  send me.
- **What to do when `docs/plans/` does not exist yet.** Never mentioned. `Write` handles it, but
  the commit in 6.3 `git add`s a path in a directory that is brand new and untracked — fine here,
  worth one word.
- **Whether a feature worktree is allowed to be the cwd at all.** 6.1 acknowledges the case; the
  prerequisites (`git rev-parse --show-toplevel` for `.weside/dor.md`) and the graphify commands
  (bare relative `scripts/graphify/...`) do not. In this repo the graph would build in whichever
  worktree I stand in — the weside-core convention is that it builds only in main. No guidance.
- **A criterion for "more than one sitting"** and hence for printing the `/loop` line. (D14)
- **Where the `.weside/verify.md` proposal goes in the plan.** Documentation Impact? Verification?
  I put it in both. (D13)
- **Any statement of what happens to a `--solo`-vs-dispatch recommendation the user ignores.**
  Cosmetic, but the skill spends a whole section on a recommendation it then calls non-binding.

---

## Cuttable — lines I obeyed without needing to be told

> `SKILL.md:117` — "Research codebase thoroughly, then create detailed plan."

Writing a plan without reading the codebase is not a thing an Opus session does. Pure filler at
the head of the step whose real content is the four paragraphs after it.

> `SKILL.md:136` — "Read the top 3-5 results to understand existing patterns, primitives, and ADRs
> that apply."

I read search hits. The number is arbitrary and I ignored it (there was one hit).

> `SKILL.md:91` — "explore the codebase instead of asking whenever the answer is discoverable there"

Default behaviour. Nobody asks the user which file the navigator is in.

> `SKILL.md:159` — "Empty rows are fine if nothing was discussed."

Permission I did not need for a table I filled.

> `SKILL.md:259` — "**Execute these 6 commands IN ORDER. No explanations. No summaries between
> steps.**" and `SKILL.md:257` — "⛔ **ExitPlanMode approval = "continue executing Step 6", NOT
> "stop and summarize"!**"

Two lines, one instruction, plus a third at 301 ("⛔ **STOP after step 6**") and a fourth at 395
("⛔ NEVER implement… after Step 6, STOP IMMEDIATELY"). Four ⛔ markers for two behaviours. The
prohibition on implementing is worth **one** line, not four.

> `SKILL.md:389-395` — the entire "## Rules" block.

Self-described as redundant: "The sections above are the spec". Of its seven bullets, five restate
the body verbatim (ticket MINIMAL; `-story.md` suffix; `epic:` frontmatter; coherent-change-is-not-
an-epic; never implement). Only two carry anything new (living plans, user-visible surfaces owe a
proof block) — and the proof-block rule duplicates the Verification section's job.

> `SKILL.md:353-357` — "### Level 1: No vision configured / Skip vision checks. Just verify ACs and
> plan quality."

A named level for "do the thing you were already doing". Also overlaps the Training-on-the-Job
section immediately below, which fires on the same condition.

> `SKILL.md:322` — "The recommendation is non-binding — always offer the other surface as the
> fallback line."

Step 6.6 already prints the fallback line in its literal template.

> `SKILL.md:16` (the APO blockquote) restates the Execution Surface section's thesis, which the
> Execution Surface table restates, which the heuristic bullets restate, which Step 6.6 restates.
> Four statements of "dispatch unless trivial".

---

## Grade

**2/5.** The skill's *thinking* is good — the grill-style interview, brainstorm-before-ACs, the
coherent-phased-change-is-not-an-epic rule, the verification oracle ladder and the phase/Files/
`parallel_groups` contract all produced a genuinely better plan than I would have written unaided,
and the vague-sentence handling worked exactly as designed once I found it. But scenario (b) is
the mode the skill is *least* finished for, and it fails on mechanics rather than judgement.
`{TICKET}` — the token every downstream artifact is keyed on — is undefined the moment ticketing
is not Jira, and no file in the chain fills the gap (D2); Step 6.1 reads a path built from an
undefined `{codename}` (D3); 6.2 contradicts both 6.1 and Create Mode's own numbered list, so a
literal CREATE run opens two issues and cannot satisfy its own ordering (D5); 6.3 pushes to a
protected `main` unasked and misreports which half of the chain failed (D6); and the plan template
the skill emits does not match `docs/plan-format.md`, the document that calls itself the versioned
contract (D15). Of Step 6's six commands, exactly one — the checkpoint — runs verbatim in this
world. Create Mode itself is five lines that delegate their hardest step ("design session") to a
protocol in another mode that they never cite (D7), which means the section handling the vaguest
input carries the least instruction. Against that, roughly a fifth of the file is restatement:
four ⛔ blocks for two prohibitions, a Rules section that admits it is a recap, and four separate
statements of the dispatch heuristic. Shortening this skill is not in tension with fixing it —
the redundant fifth is where the room for the six missing definitions comes from.
