<!-- markdownlint-disable -->

# Round 2 — Scenario (b)

Table-top re-run of `/we:story "make onboarding less painful"` against the revised
`we/skills/story/SKILL.md`. Nothing executed; every call below is the call I *would* have made,
in order. `[UNPROMPTED]` marks a line I obeyed that I would have done without being told.

## Trace

### 0 — World

Session Opus, mode `acceptEdits`. cwd `/home/user/app`, branch `chore/cleanup`; main worktree
`/home/user/app-main`. No `.weside/`, no `CONTEXT.md`, no `docs/` at all. No TurboVault, no
`superpowers`. graphify installed. `gh` authenticated.

### Prerequisites

1. `Read(".../we/quality/dor.md")` — done.
2. `Read(".../we/references/verification.md")` — done.
3. `Read(".../we/references/long-running.md")` — done.
4. `Bash("git rev-parse --show-toplevel")` → `/home/user/app`.
   **Guessing point (unchanged from round 1):** I am in a *feature* worktree. The prerequisite
   says "resolve the repo root"; Step 5.0 goes to real trouble to find the *main* worktree
   instead. Same repo, two different roots, and only one of the two places says which it means.
   `.weside/` is committed content so both would carry it — but the skill does not say that, I
   inferred it.
5. `Bash("test -f /home/user/app/.weside/dor.md")` → absent → plugin DoR only, silently.
6. `Bash("test -f /home/user/app/CONTEXT.md")` → absent. Glossary read skipped; Step 2's
   "offer to create it" is now live and I hold it for later.

No "verify setup / suggest `/we:setup`" step exists any more — the whole `.weside/`-absence
paragraph round 1 quoted is gone. I emitted nothing about it.

### {TICKET} resolution — the first real fork

7. `Bash("command -v gh && gh auth status")` → authenticated.
8. `Bash("gh issue list --limit 1")` → works; newest issue is `#41`.

The skill: *"`{TICKET}` is the ticketing key; with no ticketing tool it is a kebab-case slug of
the story title. The same token names the plan file, the frontmatter `story:`, the checkpoint and
the branch — **pick it once, in Step 1**, and never vary it."*

Two problems fire here at once, and both are about **create mode specifically**:

- **Step 1 never runs in create mode.** The Modes table routes `/we:story "description"` as
  *Step 2 → create ticket → Steps 3–5*. Step 1 is not in that list. So the single sentence that
  anchors the most load-bearing token in the skill points at the one step this mode skips. I
  improvised: I treat "pick it once" as binding wherever the pick actually happens (at ticket
  creation, between Step 2 and Step 3).
- **"the ticketing key" is still undefined for GitHub Issues.** ticketing.md ranks `gh` third and
  never says what a GitHub key *looks like*. Candidates and their damage, all mine to weigh:
  `42` (plan `docs/plans/42-story.md`, branch `feat/42-…`, checkpoint key `42` — ugly, and a
  bare integer collides with nothing but reads like a version number); `#42` (illegal in a
  branch name, and `#` starts a comment in the frontmatter parser); `gh-42` (readable, but the
  user then types `/we:orchestrate gh-42` and orchestrate Step 1's "every ticket **with
  comments**" runs `gh issue view gh-42` → fails, exactly round 1's finding).
  **I picked `42`** — it is the only one that survives both the filename and a later `gh issue
  view`. I verified the downstream survives it:
9. `Bash("grep -n '_parse_frontmatter' -A30 we/scripts/orchestration.py")` (as a sanity read on my
   choice) → the CLI's frontmatter parser is a hand-rolled stdlib one that keeps every value as a
   **string**, so `story: 42` does not become an int. `feat/42-*` matches orchestrate Step 2's
   `git branch --list`. `docs/plans/42-story.md` matches orchestrate Step 0. Choice holds — but
   I had to prove that myself; the skill neither blessed nor forbade it.

### Step 2 — Understand (INTERACTIVE)

`superpowers` absent → targeted questions. The Modes table now sends create mode *into Step 2
first*, which is where the brainstorm-before-ACs protocol lives — round 1's D7 complaint is
structurally answered, and it changed my behaviour: I did not write a single AC until Q4.

10. `Glob("**/*.{tsx,ts}")` / `Glob("app/**/*.py")` — orient on the stack. Expo Router app under
    `mobile/app/`, FastAPI under `api/app/`. `[UNPROMPTED]`
11. `Grep(pattern="onboarding|first.?run|welcome", include="*.tsx")` → 0 hits. Nothing exists.
12. `Grep(pattern="companions", include="*.tsx")` → `mobile/app/(tabs)/companions.tsx`, which
    renders `<EmptyState title="No companions yet" />`. This is the screen the user means.
13. **Q1** — "Which moment is painful: signup, the first screen after signup, or something later?
    My recommendation: the first screen after signup, because that is where I find an
    `EmptyState` with no next action." → `[USER]` "the empty screen".
14. **Q2** — "What should a new user be able to *do* from that screen, in one sentence? My
    recommendation: pick one of a few ready-made starter companions and land in a working chat."
    → `[USER]` "yeah something like that".
15. **Q3** — "Do you want the guided flow to appear once and never again, or to stay reachable
    from a menu? Recommendation: once, dismissible, with a persisted flag — a re-openable tour is
    a second surface nobody maintains." → `[USER]` "once is fine".
16. **Q4** (the answer that turned concrete) → the user: *"a new user lands on an empty companion
    list with no idea what to do next; I want a first-run guided flow — a couple of starter
    companions the backend can hand out, a screen that walks them through it, and it shouldn't
    come back after they've seen it."*
17. **Glossary offer:** "onboarding" got resolved to **first run** (the flow) vs **signup** (the
    auth step). Skill says offer to record it in `CONTEXT.md` and *"offer to create the file if
    it does not exist"* — the exists-guard round 1 asked for is there now.
    → **Q5** "Create `CONTEXT.md` with `first run` / `signup` and mark `onboarding` as
    `_Avoid_`?" → `[USER]` "sure". Held for Step 5.1's commit, as the skill says.
18. `.weside/vision.md` absent → skipped **silently**. Nothing printed. (Round 1's "never ask
    again with no store" line is gone; there is nothing left to ask.)
19. **Size check.** The skill's two shapes: this is *one coherent change with several phases*
    (a seed endpoint, a screen, a persisted gate — one user-visible outcome, one PR), not many
    independent slices. → single Story, phased plan, no `/we:epic` print, no stop. Correct branch,
    and the skill made the call for me rather than leaving it to taste.

### Between Step 2 and Step 3 — create the ticket (the Modes table's own ordering)

19a. `Bash("gh issue create --title 'First-run guided onboarding' --body-file /tmp/body.md")`
    -> `https://github.com/acme/app/issues/42`. Body is Step 5.3's minimal template:
    ```markdown
    ## User Story
    As a new user I want a guided first run so that I know what to do with an empty companion list.

    ## Plan
    Implementation Plan: docs/plans/42-story.md
    ```
    **The chicken-and-egg I had to walk around:** the body must name `docs/plans/{TICKET}-story.md`,
    and with GitHub Issues `{TICKET}` *is the number this call returns* — it does not exist until
    the call completes. So the body cannot be written in one pass; I wrote a placeholder link that
    Step 5.3's re-set later corrects. That is what makes 5.3 load-bearing rather than cosmetic,
    and nothing in the skill says so.
19b. `{TICKET}` is now fixed at `42` for the rest of the run: plan file, frontmatter `story:`,
    checkpoint key, branch prefix.

### Step 3 — Create Plan (EnterPlanMode)

20. `EnterPlanMode`.
21. TurboVault absent → emit **once**: *"⚠️ TurboVault unavailable — using grep fallback;
    architecture context may be incomplete. Check the MCP config."*
22. `Grep(pattern="onboarding", include="*.md")` — **no `path="docs/"` any more**, so this does
    not error in a repo with no `docs/`. Returns `README.md` only. (Round 1's D11 would have
    errored here.)
23. `Glob(pattern="docs/architecture/**/*.md")` → empty. Harmless.
24. **Blast radius.** `.weside/config.json` does not exist → `tools.graphify` is absent → the
    skill forbids the graph and orders the `rg` path plus a self-declaration in the plan.
    **This is where the revision cost me a real capability:** graphify *is* installed here. The
    gate is a config file that only `/we:setup` writes, in a repo that has no `.weside/` — so in
    every un-set-up repo the graphify branch is unreachable by construction, and the plan carries
    "grep-derived — no code graph" while the graph tool sits on `$PATH`. I obeyed it.
25. `Bash("rg -n 'EmptyState' mobile/ --type tsx -l")` → 3 call sites; only `companions.tsx` is
    the entry point. `[UNPROMPTED]`
26. `Bash("rg -n 'router\\.(push|replace)' mobile/app -l")`, `Bash("rg -n 'class User' api/app -n")`
    → the `users` model file and the Alembic dir, for the Files lists. `[UNPROMPTED]`
27. `.weside/verify.md` absent → the template's own line now tells me what to do
    (*"absent → say so once and propose it under Documentation Impact"*), so I said it once and
    put the proposal in exactly one place. Round 1 had to invent the slot and put it in two.
28. Compose the plan (below). `parallel_groups: [[1, 2]]` — backend files and mobile files are
    disjoint and Phase 2 is presentational only; Phase 3 is the wiring and stays serial.
    **Note I had to reason around:** the group `[[1,2]]` starts at phase 1, and orchestrate's
    rule is "a group runs after every *lower-numbered* phase has merged" — there are none, so it
    is a wave-0 group. Legal, but neither the skill nor plan-format.md shows a group containing
    phase 1, and I hesitated.
29. **Frontmatter trap I stepped around by hand.** The template's frontmatter lines carry
    trailing `#` comments (`epic: {EPIC-SLUG-OR-KEY}  # REQUIRED when …`,
    `depends_on: []            # optional: …`, `parallel_groups: []       # optional: …`).
    `orchestration.py`'s `_parse_frontmatter` does **not** strip inline comments and only
    recognises a list when the value starts `[` and ends `]`. Copied verbatim,
    `depends_on: []   # optional: story keys that must merge first` parses to the one-element
    list `["[]   # optional: story keys that must merge first"]` — a phantom dependency that can
    never resolve, which holds the story out of the ready set forever. I stripped the comments.
    Nothing told me to. See N4.

### Step 4 — ExitPlanMode

30. `ExitPlanMode(plan=<the plan below>)` → approved.

### Step 5 — post-approval, in order

31. **5.0** `Bash("git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\\/heads\\/main$/{print p; exit}'")`
    → `/home/user/app-main`. This runs **first** now, and 5.1 and 5.4 both consume `$MAIN_WORKTREE`
    — the two-places-one-lookup split round 1 flagged is gone.
32. **5.1** `Write("/home/user/app-main/docs/plans/42-story.md", …)` with `status: approved`,
    `story: 42`. `docs/` does not exist; `Write` creates it. Still nowhere stated, still fine.
33. **5.1b** `Write("/home/user/app-main/CONTEXT.md", …)` — the accepted glossary entry, written
    now, as the skill says, so 5.4 can carry it. **But 5.4's `git add` names only the plan file**
    (`git add docs/plans/{TICKET}-story.md`), so the `CONTEXT.md` I was just told to write is not
    in the commit. I added it by hand. See N3.
34. **5.2** `Read` the file back and run the 3-item `dor-scan`: `Given`/`When`/`Then` present ✓;
    `## Context` > 50 chars ✓; `^### Phase \d+:` present ✓. Pass.
35. **5.3** Ticket, one pass. The issue was created at step 19a per the Modes
    table; here I *set* its description to the minimal body — so **no double-create**, round 1's
    two-issues outcome does not happen. Ordering note below.
    `Bash("gh issue edit 42 --body-file /tmp/body.md")`,
    `Bash("gh issue comment 42 --body …")` naming the one contradiction I resolved ("onboarding"
    → first run vs signup) and the one question I parked (whether starter companions are
    seeded per-locale).
    Transition: GitHub Issues has no status transitions → ticketing.md says **skip silently**.
    Skipped.
36. **5.4** the commit block, verbatim:
    ```
    [ -n "$MAIN_WORKTREE" ] || { echo "WARN: no worktree on main — plan saved, not committed."; exit; }
    cd "$MAIN_WORKTREE" || exit
    git add docs/plans/42-story.md && git commit -m "docs: add 42 plan — First-run guided onboarding" || { echo "WARN: commit failed …"; exit; }
    git push || echo "WARN: committed locally, push failed (branch protection?) — push by hand."
    ```
    The empty-`MAIN_WORKTREE` guard is there, and commit-failed and push-failed now say different
    things. **The push still fires unasked**, straight at `main`, as an automatic consequence of
    approving a *plan*. I ran it because the skill told me to, and I would not have.
    Also: `docs: add 42 plan — …` is what the literal substitution produces. That subject line is
    unreadable, and it is the first thing the `{TICKET}`-is-a-bare-integer choice costs.
37. **5.5** `Bash("python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint 42 refined")`
    → the script exists and `story_key` is free text, so this is executable verbatim.
38. **5.6** TurboVault absent → skipped silently.
39. **5.7** Output. Long-running trigger from `long-running.md` is now **structural**: 4+ phases,
    or non-empty `depends_on`, or the user says they will be away. I have 3 phases, empty
    `depends_on`, no absence → **no `/loop` line printed**, and I did not have to guess. Round 1
    could not decide this.
    ```
    Plan saved to docs/plans/42-story.md. /we:story DONE.
    State file: docs/plans/42-state.md (the Lead creates it on the first run).

    Recommended next: /we:orchestrate 42   ← 3 phases; phases 1+2 parallelise (backend/mobile
    disjoint), phase 3 wires them — dispatch keeps this session out of the diff.
    (or /we:orchestrate 42 --solo if you'd rather run it inline.)
    ```
40. STOP.

**Executability of Step 5 in this world:** 5.0 ✓, 5.1 ✓, 5.2 ✓, 5.3 ✓ (`gh` path; transition
correctly skipped), 5.4 ✓ mechanically (push may 403 and says so), 5.5 ✓, 5.6 correctly skipped (no
TurboVault), 5.7 ✓. Round 1 counted exactly one of six commands as runnable verbatim; here
**every one of Step 5's eight items runs as written**, with 5.6 skipped by its own condition.

---

## The plan I would have written

**Path:** `/home/user/app-main/docs/plans/42-story.md`
(main worktree from Step 5.0, *not* the `/home/user/app` I am standing in.)

```markdown
---
type: story-plan
story: 42
depends_on: []
comments_read_through: none
created: 2026-08-27
status: approved
parallel_groups: [[1, 2]]
---

# Plan: First-run guided onboarding

## Context

A new user finishes signup and lands on the companions tab, which renders an empty state with a
title and no next action — there is nothing to tap and nothing that says what a companion is for.
That dead end is what "make onboarding less painful" turned out to mean; signup itself is fine and
is out of scope. The user wants a guided first run: the backend hands out a small set of ready-made
starter companions, a screen walks the new user through picking one, and the flow does not come
back once it has been completed. "Once is fine" was explicit — no re-openable tour, no menu entry,
because a second entry point is a second surface to maintain. The persisted flag lives server-side
rather than in device storage so a reinstall or a second device does not replay the flow. Nothing
called "onboarding" exists in the codebase today, so there is no prior art to match and no
migration of existing users beyond backfilling the flag as already-seen.

## Acceptance Criteria

1. **Given** a signed-in user who has never completed the first run **When** they open the
   companions tab with no companions **Then** the first-run guide is shown instead of the bare
   empty state, offering at least three starter companions.
2. **Given** the first-run guide is open **When** the user selects a starter companion and
   confirms **Then** that companion is created for them and they land in its chat.
3. **Given** a user who has completed the first run **When** they reopen the app, reload the web
   build, or sign in on a second device **Then** the guide is not shown again, even with an empty
   companion list.
4. **Given** an existing user created before this story **When** they open the companions tab
   **Then** the guide is not shown — existing users are backfilled as already-seen.
5. **Given** the starter-kit endpoint is unreachable **When** the companions tab loads **Then**
   the previous empty state is rendered and no error dialog blocks the screen.

## User Journey

> **This story is only DONE when the user can experience the journey end-to-end.**

1. New user finishes signup and opens the companions tab. 2. Instead of "No companions yet" they
see a short guide with three starter companions. 3. They tap one, confirm, and the companion is
created. 4. They land in that companion's chat; reloading the app never shows the guide again.

## Testing Requirements

- Unit tests for the starter-kit serializer and for the completion flag's backfill default.
- Unit tests for the guide screen's gate: shown when `completed_at` is null AND the list is empty;
  not shown in either other case; not shown when the fetch fails (AC 5).
- Integration tests for `GET /v1/onboarding/starter-kit` and `POST /v1/onboarding/complete`
  against a **real Postgres** (`pytest api/tests/integration/test_onboarding.py`, database
  `app_test`, `alembic upgrade head` first) — the completion write is idempotent and the second
  POST must not error.
- Migration test: the backfill sets `onboarding_completed_at` for every pre-existing user row.

## Verification

> This repo has **no `.weside/verify.md`** — said once here, and proposed under Documentation
> Impact. Verification below uses what the stack offers: `uvicorn` + `curl` for the API, the Expo
> web build for the screen.

- **Oracle:** ui — AC 1 and 3 are about what a user *sees* on a screen, and reachability is the
  whole point of the story; an endpoint nothing calls answers 200 all day. The API half is
  asserted with oracle 1 underneath it.
- **Seed:** `python -m app.cli seed:user --fresh --email first-run@example.test` (see *Missing CLI
  verb*), then `uvicorn app.main:app --reload` and `yarn workspace mobile expo start --web`.
- **Asserted:** `GET /v1/onboarding/starter-kit` → 200, `items[]` length ≥ 3, each with `id`,
  `name`, `blurb`. In the web build, the companions tab renders the accessibility label
  "Choose your first companion"; tapping the first card and confirming navigates to
  `/companion/<id>`; `POST /v1/onboarding/complete` → 204; a browser reload lands on the empty
  state, not the guide.
- **Not proven:** native iOS/Android rendering and gesture behaviour of the guide (web build
  only), and cross-device propagation of the flag beyond a second browser session. Owed by a
  manual device round before the store build; the human owns it.
- **Exit criterion:** on a fresh DEV database, `seed:user --fresh` followed by the web walkthrough
  shows the guide exactly once and never again after completion, and
  `api/tests/integration/test_onboarding.py` is green — runnable by someone who was not in this
  session.
- **Missing CLI verb:** `seed:user --fresh` does not exist; today creating a never-onboarded user
  is a psql dance. It ships in **Phase 1**, which is as early as its own dependency (the new
  column) allows.

## Technical Approach

**Patterns:** starter companions come from a static seed list in the API layer, not a new table —
three rows of content do not earn a schema. The completion flag is a nullable timestamp column on
`users`, not a boolean, so "when" is recoverable. The mobile gate is a single hook consumed by the
companions tab; no new navigation stack. The guide screen is presentational and holds no API
knowledge, so it can be built before the client is wired (which is what lets Phases 1 and 2 run
in parallel).

`Files:` lists are grep-derived — no code graph. (graphify is installed, but `.weside/config.json`
does not exist, so `tools.graphify` is absent and the skill's rg path applies. The disjointness
guard behind `parallel_groups` is therefore worth a grep, not a call graph — the Lead should
re-check the intersection at dispatch.)

Architecture context: TurboVault is unavailable; the grep fallback found no architecture docs in
this repo (`docs/` does not exist), so there is no prior decision this composes with.

## Implementation Phases

### Phase 1: Backend starter kit, completion flag, and a seed verb
- **Goal:** the API can hand out starter companions, record that a user finished the first run,
  and put a fresh user on disk for verification.
- **Files:** `api/app/api/onboarding.py` (new), `api/app/api/__init__.py` (router registration),
  `api/app/schemas/onboarding.py` (new), `api/app/content/starter_companions.py` (new),
  `api/app/models/user.py` (`onboarding_completed_at`), `api/alembic/versions/<rev>_onboarding_completed_at.py`
  (new — add column + backfill existing rows to `now()`), `api/app/cli.py` (`seed:user --fresh`),
  `api/tests/integration/test_onboarding.py` (new), `api/tests/test_user_model.py` (existing —
  its `User(...)` construction sites break on the new column), `openapi.json` (regenerated).
- **Risk:** migration — a column plus a backfill on `users`; the backfill is what keeps AC 4 true,
  and getting it wrong replays the flow for every existing user.
- **Approach:** additive nullable column, backfill in the same revision, two endpoints
  (`GET /v1/onboarding/starter-kit`, `POST /v1/onboarding/complete`). The POST is idempotent —
  a second call is a 204, not a 409. Regenerate `openapi.json` in this phase so Phase 3 has a
  typed client to generate from.

### Phase 2: The first-run guide screen
- **Goal:** a self-contained screen that presents starter companions and a confirm action, driven
  entirely by props.
- **Files:** `mobile/components/FirstRunGuide.tsx` (new), `mobile/components/StarterCard.tsx`
  (new), `mobile/components/__tests__/FirstRunGuide.test.tsx` (new).
- **Risk:** ordinary.
- **Approach:** presentational only — takes `items`, `onSelect`, `onDismiss`; owns no fetching and
  no navigation. Accessibility labels are part of the contract (they are what Verification
  asserts on), so they are written here, not retrofitted.

### Phase 3: Wire the gate into the companions tab
- **Goal:** a new user with an empty list sees the guide, completes it once, and never again.
- **Files:** `mobile/api/client.ts` (regenerated from `openapi.json`),
  `mobile/hooks/useFirstRun.ts` (new), `mobile/app/(tabs)/companions.tsx` (empty-state branch),
  `mobile/app/(tabs)/__tests__/companions.test.tsx` (existing — the empty-state assertion changes),
  `mobile/hooks/__tests__/useFirstRun.test.ts` (new).
- **Risk:** ordinary.
- **Approach:** `useFirstRun` fetches the flag and the starter kit together and returns
  `{ shouldShow, items }`; a failed fetch returns `shouldShow: false` so the old empty state
  survives (AC 5). Completion POSTs, then navigates to the created companion's chat.

## Constraints and Pins

**Constraints:** the new endpoints register through the existing API router module rather than a
second app mount; the migration is additive-then-backfill in one revision so a rolling deploy is
safe; the mobile client is generated from `openapi.json`, never hand-written.

**Pins:** the companions tab's existing empty state must still render verbatim for any user whose
`onboarding_completed_at` is set, and when the starter-kit fetch fails. Existing users must never
see the guide — the migration backfill is what holds that, and a test asserts it against the
migrated database, not against a model default.

## Design Decisions

| Decision | Alternatives Considered | Why This |
|---|---|---|
| Server-side `onboarding_completed_at` on `users` | device-local storage (AsyncStorage); a separate `user_onboarding` table | The user said "once is fine" and meant it across devices; local storage replays the flow on reinstall and on a second device. A separate table is a join for one nullable timestamp. |
| Nullable timestamp, not a boolean | `onboarding_seen BOOLEAN` | Same cost, and "when" is recoverable for later analysis of where users drop. |
| Starter companions as a static content module | a `starter_companions` table with an admin surface | Three rows of copy do not earn a schema or a CRUD surface; a table would also pull a seeding step into every environment. Revisit if the set becomes per-locale — that question is parked on the ticket. |
| One-shot flow, no re-openable tour | a "Show me around again" menu entry | Explicit user decision; a second entry point is a second surface to maintain and neither AC nor journey asks for it. |
| Guide screen built presentational, wired in a later phase | one phase that builds and wires it | It is what makes Phases 1 and 2 genuinely disjoint (backend files vs mobile component files) and lets them run as one wave. |
| Failed fetch falls back to the old empty state | block with an error dialog | A first-run flow that can hard-fail a new user's first screen is worse than no flow; AC 5 pins it. |

## Code Guidance

**DO:** put the accessibility labels the Verification block asserts on into Phase 2's components;
keep `useFirstRun` the only place that decides `shouldShow`; make `POST /complete` idempotent;
backfill in the same Alembic revision that adds the column.
**DON'T:** read or write the flag from device storage; add a second navigation stack for the
guide; hand-edit `mobile/api/client.ts`; let a starter-kit fetch failure surface as a dialog.

## Security Review Required

No — the endpoints are authenticated user-scoped reads and one self-write of a flag on the caller's
own row; no new PII, no new trust boundary, no cross-tenant read. The one thing to keep honest is
that `POST /complete` writes the *caller's* row and takes no user id.

## Documentation Impact

- **Docstrings** — `api/app/api/onboarding.py` carries why the flag is server-side and why the
  POST is idempotent; `mobile/hooks/useFirstRun.ts` carries the three-way gate and the
  fail-to-old-empty-state rule.
- **Architecture doc** — none; this repo has no `docs/` and the change adds no cross-module
  interplay.
- **ADR** — no.
- **Generated** — `openapi.json` (Phase 1) and `mobile/api/client.ts` (Phase 3).
- **New doc** — `.weside/verify.md` **is proposed in this PR**: this repo has no verification
  recipe, so "how DEV comes up, which CLI verbs seed a user, how the web build is driven" lives
  nowhere and every later story re-derives it. The code cannot hold it because it is about
  running the system, not about any one module.
```

---

## Round-1 verdict table

| # | Round-1 defect | Verdict | Evidence from this run |
|---|---|---|---|
| D1 | "no `.weside/` ⇒ no ticketing ⇒ Plan-only" false chain | **FIXED** | The whole "Verify setup" paragraph is gone from the skill. At trace step 6–8 nothing pushed me toward Plan-only; I went straight to ticketing detection and ended up on GitHub Issues, which is correct. Small loss: there is now no `/we:setup` hint at all in a repo that plainly needs one. |
| D2 | `{TICKET}` undefined outside a Jira-shaped world | **PARTIALLY FIXED** | The Output table now defines the *no-tool* case ("kebab-case slug of the story title") and pins the token across filename/frontmatter/checkpoint/branch. It still does **not** define the GitHub-Issues case, which is the case this world is in. At step 8 I had to invent `42` vs `#42` vs `gh-42` and prove downstream survival myself (step 9). The new wording is arguably *more* dangerous than round 1's silence: "the ticketing key" reads as answered. |
| D3 | `{codename}` defined nowhere | **FIXED** | Step 5.1 reads "write the approved plan to `$MAIN_WORKTREE/docs/plans/{TICKET}-story.md`". No `~/.claude/plans/{codename}.md` anywhere; at step 32 there was nothing to guess and no `ls ~/.claude/plans` in my trace. |
| D4 | main-worktree resolution specified twice, differently | **FIXED** | Step 5.0 resolves `MAIN_WORKTREE` once, before anything uses it; 5.1 and 5.4 both consume `$MAIN_WORKTREE`. At step 31 the awk recipe found `/home/user/app-main`; the prose heuristic that would have pointed me at `/home/user/app` is gone. |
| D5 | Create Mode and Step 6.2 both claim ticket creation | **FIXED** | The Modes table now says create the ticket *between Step 2 and Step 3*, "(Step 5.3's body)", and Step 5.3 says **set** the description, not create it. At steps 35 I edited one issue; I never opened a second. The ordering impossibility is gone too — the number exists before Step 3 writes the plan filename. Residual, not a re-open: with GitHub Issues the body must name the plan file, whose name *is* the number the create call has not returned yet (step 19a) — so the minimal body is unwritable in one pass and 5.3's re-set is load-bearing, not cosmetic. Nothing says that. |
| D6 | Step 6.3 pushes to `main` unconfirmed and mislabels failures | **PARTIALLY FIXED** | The failure-labelling half is fixed: at step 36 the empty-`MAIN_WORKTREE` guard fires before any `cd`, and commit-failure and push-failure print different, accurate messages. The **push still fires automatically** at `main` as a consequence of approving a plan — I ran it because the skill told me to, and the user sanctioned a plan, not a push. |
| D7 | Create Mode delegates its hardest step to an uncited protocol | **FIXED** | The Modes table routes `/we:story "description"` through **Step 2 first**, and Step 2 is where brainstorm-before-ACs lives. This changed my run: steps 13–16 are four questions before a single AC. A session that jumped straight to the mode row is now sent to the right place by that row. |
| D8 | "never ask again" has no store | **FIXED** | The line is gone. Step 2's vision branch is now "No vision configured → skip silently", which at step 18 I executed with nothing to remember and nothing to ask. |
| D9 | glossary capture assumes `CONTEXT.md` exists | **FIXED** | Step 2 now reads "offer to record it in the project glossary (`CONTEXT.md` …) — offer to create the file if it does not exist, and write it in Step 5.1's commit". At step 17 the offer was well-formed in a repo with no such file. (The write-it-in-the-commit half then trips over 5.4's `git add` — see N3.) |
| D10 | "Link to Epic (if applicable)" dead-ends on GitHub Issues | **FIXED (skill) / FORK (dor.md)** | The dead-end step no longer exists in the skill; `epic:` is now a frontmatter field with an explicit "omit for standalone stories", which is what I did. But `quality/dor.md` still carries **Ticket linked — Connected to parent Epic (if using ticketing tool)** as a *Required (Blocking)* row, and I *am* using a ticketing tool that has no parent field, so read strictly my story still fails a DoR row no action can satisfy. That file is outside this worker's list → FORK. |
| D11 | grep fallback hard-codes `path="docs/"` | **FIXED** | Step 3's fallback is now `Grep(pattern="<topic keyword>", include="*.md")`. At step 22 it ran clean in a repo with no `docs/`; the surviving `Glob("docs/architecture/**/*.md")` returned empty, which is not an error. |
| D12 | "Read the plan and the files it names in full" in the wrong skill | **FIXED** | The impossible-read sentence is gone; what remains is "Load more files than feel necessary; a wrong assumption costs more than a wide read", which is what I acted on at steps 25–26. |
| D13 | no-`.weside/verify.md` obligation never reaches the SKILL | **FIXED** | The plan template's Verification blockquote now ends "commands live in `<repo>/.weside/verify.md` — absent → say so once and propose it under Documentation Impact." At step 27 I said it once and had exactly one slot to put the proposal in; round 1 put it in two because nothing told it where. |
| D14 | "spans more than one sitting" unjudgeable | **FIXED** | `long-running.md` now: "the plan has 4+ phases, or a non-empty `depends_on:`, or the user says they will be away." At step 39 that resolved mechanically — 3 phases, empty `depends_on`, no absence → no `/loop` line, no judgement call. The skill also now gates the print on the plan naming a *scriptable* oracle, which is a stronger contract than round 1 asked for. |
| D15 | SKILL template vs `docs/plan-format.md` disagree | **FORK (widened)** | `plan-format.md` is outside this file list, so not a failure of the revision — but the gap got **larger**, not smaller. The skill now emits `type`, `epic`, **`depends_on`** and **`comments_read_through`** plus `## Verification`, `## Constraints and Pins`, `## User Journey`; `plan-format.md`'s frontmatter table still lists only `story`, `created`, `status`, `parallel_groups`, and its Full Template has none of those sections. My plan at step 32 conforms to the skill and would be rejected by anything validating against the self-declared "versioned contract". |
| D16 | `status: approved, story: {TICKET}` is not YAML | **FIXED** | Step 5.1 now reads "with `status: approved` and `story: {TICKET}` in the frontmatter" — two facts, no inline mapping to copy. |

**Score:** 11 FIXED, 2 PARTIALLY FIXED (D2, D6), 1 FIXED-with-FORK-residue (D10), 1 FORK (D15),
0 STILL OPEN.

---

## New defects introduced by the revision

### N1 — "pick it once, **in Step 1**" names the one step create mode skips — *blocking-adjacent*

> Output table: "The same token names the plan file, the frontmatter `story:`, the checkpoint and
> the branch — pick it once, **in Step 1**, and never vary it."
> Modes table: `/we:story "description"` → "run Step 2 first, then create the minimal ticket
> (Step 5.3's body), then Steps 3–5."

Step 1 is not in create mode's route. So the sentence that anchors the most load-bearing token in
the skill is anchored to a step that never runs in the mode where the token is hardest to pick.
The fix D5 introduced (creating the ticket between Step 2 and Step 3) is exactly the right place —
it just is not the place the anchor names. At step 8 I improvised the binding.

Step 1 owns **three** things create mode never reaches: the `{TICKET}` pick, the
`comments_read_through:` value (see N2b), and the refine-in-place check. Only the first is
re-homed by the Modes table.

**Smallest fix:** drop "in Step 1" and say "pick it at the first step that names it — Step 1 in
refine mode, the ticket creation in create mode" — and give create mode the other two explicitly.

### N2 — the `{TICKET}` definition now looks complete while the middle case is missing — *blocking*

Round 1 said nothing about non-Jira keys; the revision says "the ticketing key; with no ticketing
tool it is a kebab-case slug". Detection ranks four tools, and the definition covers ranks 1–2
(Jira keys) and rank 4 (none). **Rank 3, GitHub Issues, is the gap**, and it is the rank most
repos land on. My choice of `42` produces `docs/plans/42-story.md`, `feat/42-…`, and the commit
subject `docs: add 42 plan — First-run guided onboarding`, which is what a bare integer costs.
`gh-42` reads better and breaks orchestrate's `gh issue view`. Two sessions on the same repo will
choose differently and produce two plan files for one story.

**Smallest fix:** one clause — "GitHub Issues: the bare issue number (skills prefix nothing; the
plan file is `docs/plans/<n>-story.md`)."

### N2b — create mode's own Step 5.3 comment bounces the story it just refined — *blocking*

> 5.3: "add ONE comment naming each contradiction you resolved and each question you parked"
> Frontmatter: `comments_read_through: {newest comment id or timestamp, or "none"}`

In create mode there are no comments when the plan is written, so `comments_read_through: none` is
the only honest value — that is what I wrote at step 32. Then **step 35 writes a comment**: the
resolved "onboarding" ambiguity and the parked per-locale question. The plan on disk now says it
read through *nothing*, and the ticket carries an unanswered parked question that postdates it.

Run the consumer against that: orchestrate Step 1 reads "every ticket **with comments**", and
Step 3 signal 1 fires on "an open question in the ticket … an unanswered comment" — with no
`comments_read_through` to distinguish "the comments have overtaken this plan" from "this plan
already answered them", which is the exact discrimination the field exists for. Signal 5 sends a
refined story **back to the refine lane**. So create mode, followed literally, produces a story
that bounces on an artifact it wrote itself, one step after writing it.

This did not merely read wrong to me — it is the ordering my own trace produced: 32 writes
`none`, 35 invalidates it, and nothing between them updates the plan.

**Smallest fix:** 5.3 gains a clause — "in create mode, set the plan's `comments_read_through:`
to the id of the comment you just added" — or the comment is written *before* 5.1 and its id
flows into the frontmatter.

### N3 — Step 5.1 tells me to write `CONTEXT.md`; Step 5.4 does not commit it — *friction*

> 5.1: "Write the accepted `CONTEXT.md` glossary entry, if any, now."
> 5.4: `git add docs/plans/{TICKET}-story.md && git commit …`

At steps 33/36 the glossary file I was explicitly told to write in the main worktree is left
untracked by the very commit the skill scripts. The D9 fix ("write it in Step 5.1's commit")
points at a commit that does not include it. I added `CONTEXT.md` to the `git add` by hand.

**Smallest fix:** `git add docs/plans/{TICKET}-story.md CONTEXT.md 2>/dev/null` — or say
"add the plan and any `CONTEXT.md` you wrote".

### N4 — the frontmatter template's inline `#` comments are un-parseable by the consumer — *blocking*

The template lines are:

```
epic: {EPIC-SLUG-OR-KEY}  # REQUIRED when the story belongs to an Epic — …
depends_on: []            # optional: story keys that must merge first
parallel_groups: []       # optional: [[N, M, ...], ...] — see the independence check below
```

`orchestration.py`'s `_parse_frontmatter` is a hand-rolled stdlib parser: it splits on the first
`:`, **strips no `#` comment**, and treats a value as a list only when it starts `[` and ends `]`.
Copied verbatim, `depends_on: []   # optional: …` parses to the one-element list
`["[]   # optional: story keys that must merge first"]` — a dependency key that can never be
satisfied, which silently holds the story out of every ready set. `epic:` with its comment
attached fails `_resolve_epic_identifiers` and makes the story invisible to the epic roster —
precisely the failure its own comment warns about.

**Blast radius, honestly:** this did **not** fire in my run. `depends_on` and `epic` are read by
`_load_epic_stories` and the ready-set path, both of which run for an **epic** roster; my story is
standalone and orchestrate's Mode B never calls them. So this is a finding from reading the
consumer, not from playing it — it costs nothing here and costs the whole roster the first time a
story written from this template joins an Epic. At step 29 I stripped the comments because I had
read the parser, not because the skill said so; a reader who has not will not.

**Smallest fix:** move the explanations out of the YAML block into the prose under it, and leave
the frontmatter lines bare.

### N5 — the graphify gate is unreachable in exactly the repos that need it — *friction*

> "When `.weside/config.json` → `tools.graphify` is true, ground the … `Files:` lists … in the code
> graph … When the flag is false or absent, derive the lists with `rg` and write
> "`Files:` lists are grep-derived — no code graph" into the plan."

graphify is installed here. `.weside/config.json` only exists after `/we:setup`. So in every
un-set-up repo the flag is absent by construction, the graph branch is dead code, and the plan
carries a self-deprecating line about a tool sitting on `$PATH`. The skill offers no
"`command -v graphify`" escape and no "offer to set the flag". Step 24 is where I lost the
capability; the disjointness guard behind my `parallel_groups: [[1,2]]` is now worth a grep.

**Smallest fix:** "…or `command -v graphify` succeeds" in the condition.

### N6 — Step 5.7's output line reports a path that is not where the file is — *cosmetic*

The template prints `Plan saved to docs/plans/{TICKET}-story.md`, relative — but Step 5.0/5.1 just
established the file is in the **other** worktree. Standing in `/home/user/app`, that relative
path does not exist. One word (`$MAIN_WORKTREE/`) fixes it.

### N7 — a `parallel_groups` group containing phase 1 is undescribed — *friction*

Both the skill and orchestrate define a group as running "after every lower-numbered phase has
merged". `[[1, 2]]` has no lower-numbered phase, so it is a wave-0 group — legal, and the right
shape for a disjoint backend/mobile pair, but every example in both files starts at `[[2,3]]`.
I hesitated at step 28 over whether phase 1 is allowed in a group at all.

---

## Still cuttable

The file is materially tighter than round 1's — the four ⛔ blocks are down to two, the Rules
section is down from seven bullets to three, and the Level-1/Training-on-the-Job sections are
gone. What is left that I would have done anyway:

- **Step 2, "read the codebase for anything discoverable there."** `[UNPROMPTED]` — steps 10–12
  and 25–26 are what any session does. Nobody asks the user which file the empty state is in.
- **Step 3, "Load more files than feel necessary; a wrong assumption costs more than a wide
  read."** The surviving half of D12. It is good writing and it changed nothing about my run.
- **The Execution Surface section vs. Step 5.7.** Still two statements of one heuristic: the table
  plus the two recommend-bullets, then 5.7's template which encodes the same call and prints both
  surfaces anyway. The table's four rows justify a decision that the bullets then make
  deterministically. One of the two is enough.
- **`## Rules` bullet 1 — "The plan filename suffix is `-story.md`."** Stated in the Output table,
  in Step 5.1, in Step 5.7's output template and in the Rules block. Fourth statement.
- **Step 5's "⛔ ExitPlanMode approval means 'run Step 5', not 'stop and summarize'" plus the
  closing "⛔ STOP after Step 5."** Two markers for two genuinely different behaviours now — this
  is no longer over-warned. Keep both.
- **The `parallel_groups` independence blockquote after the template** restates orchestrate Step
  5.4 verbatim. Correct duplication for a skill whose reader may not load orchestrate — but the
  last sentence ("prose like 'these can run in parallel' is invisible to the consumer") is the
  only part that changed my behaviour; the semantics recital did not.

---

## Grade

**4/5.** (Round 1 was 2/5.) This is a different skill to run. Round 1's verdict was that the
thinking was good and the mechanics were broken — of Step 6's six commands exactly one ran
verbatim; here **all seven of Step 5's run**, the two-issue create-mode contradiction is gone,
`{codename}` is gone, the main-worktree lookup happens once before anyone needs it, the commit
chain guards its own empty variable and names which half failed, the vague-sentence mode is
routed *through* the brainstorm protocol instead of past it, the `docs/`-less grep fallback no
longer errors, and the two judgement calls round 1 could not make — when to print `/loop`, where
the missing-`verify.md` proposal goes — are now decided by structure rather than by taste. Eleven
of sixteen defects are cleanly fixed and none is still open as written. It is not 5/5 for four
reasons, in descending sharpness. Create mode's Step 5.3 writes a ticket comment that its own
just-written plan claims not to have read (N2b), and orchestrate's Step-3 signal 1 then bounces
the story back to the refine lane — a self-inflicted round trip that this run produced rather than
merely implied, and the clearest evidence that Step 1 owns obligations create mode never reaches.
The frontmatter template ships inline `#` comments that the consuming parser cannot strip (N4),
which would give a plan a phantom `depends_on` and an unresolvable `epic:`; it did not fire here
because a standalone story never touches the epic roster, but it is silent and downstream when it
does. `{TICKET}` is still
undefined for GitHub Issues (N2/D2), and the revision's partial definition makes the hole harder
to notice than round 1's silence did; that token keys the filename, the branch, the checkpoint
and every later orchestrate lookup, so the one gap that remains is in the one place that cannot
afford one. And Step 5.4 still pushes to `main` on the strength of a plan approval (D6), which is
a consent question, not a shell-quoting one. Everything else I hit — the Step-1 anchor create mode
never reaches, the uncommitted `CONTEXT.md`, the graphify flag that no un-set-up repo can ever set
— is a one-clause fix. The remaining structural debt is not in this file at all: `plan-format.md`
now describes a plan shape the producer no longer emits, and `dor.md` still blocks on an
epic-link row that GitHub Issues cannot satisfy. Both are forks, and both should be cut before
the drift is load-bearing.
