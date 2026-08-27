<!-- markdownlint-disable -->

# Round 1 — Scenario (a): refine PROJ-812, contradicting comments

## Trace

Session model Sonnet, mode `acceptEdits`, Agent Teams off, cwd `/home/user/proj` (main worktree, branch `main`).
User types: `/we:story PROJ-812`.

**1.** `Read("/home/fbiebl/weside/claude-code-plugin-SIM-1-p3/we/quality/dor.md")` — Prerequisites block.

**2.** `Read(".../we/references/verification.md")` — Prerequisites block.

**3.** `Read(".../we/references/long-running.md")` — Prerequisites block.

**4.** `Bash("git rev-parse --show-toplevel")` → `/home/user/proj`. Skill: *"resolve the repo root (`git rev-parse --show-toplevel`) and check for `<repo-root>/.weside/dor.md`"*.

**5.** `Bash("test -f /home/user/proj/.weside/dor.md && echo yes")` → `yes`.

**6.** `Read("/home/user/proj/.weside/dor.md")` → one extra row: *"Every story names the rollback step."* I hold it as ADDITIVE.
→ **Guessing point.** The plugin DoR maps every one of its rows onto a named plan section. The repo row maps onto nothing, and no file says where a repo-local DoR item lands in the plan. **What I did instead:** I invented a `## Rollback` section in the plan and flagged it in the trace. A second session would plausibly put it under Technical Approach, or in Code Guidance, or drop it — and `/we:orchestrate` Step 1 says *"a plan that fails a row there goes back to the refine lane"*, so an invented slot is a coin flip on a blocking gate. → **Defect D4.**

**7.** Model-tier notice, said once, not blocking:
> "This session is Sonnet. `/we:story` writes the plan every later worker follows — `/model opus` is the recommended tier. Continuing on Sonnet."
`[UNPROMPTED]` — I would say this without being told; see *Cuttable*.

**8.** `Bash("test -d /home/user/proj/.weside && echo yes")` → `yes`. Skill: *"Verify setup: if `.weside/` doesn't exist…"*. The precondition is not met, so the whole instruction is dead this run. No action.

**9.** Ticketing detection per `references/ticketing.md`. weside MCP `JIRA_*` tools: not in my tool list → priority 1 fails. Atlassian MCP `jira_*` tools: present → **path 2**.
`ToolSearch(query="select:mcp__atlassian__jira_get_issue", max_results=1)` to load the schema, then:
`mcp__atlassian__jira_get_issue(issue_key="PROJ-812", comment_limit=20, fields="summary,description,status,parent")`
Returns summary/description/status Backlog/parent PROJ-800 and comments 1–3 as given.

**10.** `Bash("ls docs/plans/PROJ-812-story.md docs/plans/PROJ-812-plan.md 2>&1")` → both absent.
Skill Step 1: *"Check if plan already exists at `docs/plans/{TICKET}-story.md`."* — and then nothing. No branch for exists, no branch for absent. → **Defect D9.** I proceeded on the absent branch by inference.

**11.** `Bash("ls docs/plans/")` — not instructed. `[UNPROMPTED]` — I did it because the frontmatter needs `epic:` and I wanted to know what the parent's file is called. Found `docs/plans/PROJ-800-epic.md`.

**12.** `Read("docs/plans/PROJ-800-epic.md")` — **not instructed anywhere.** The SKILL demands `epic:` in the frontmatter and says a missing one *"makes the story invisible to orchestration"*, but never tells me to read the parent epic or how to derive its slug/key. See *What I needed and did not find*.

**13.** Conflict named to the user, per `ticketing.md` (*"when a comment contradicts the description, the newest statement wins and you name the conflict to the user instead of silently picking one"*):

> PROJ-812's description and its comments disagree on two points.
> 1. **Revocation timing.** Description: "revoke instantly". PO (14d): "accept a 60s window, we cache tokens 60s". Tech lead (3d): "we decided against the 60s window — the cache must be invalidated on revoke". PO (yesterday) agreed. Newest wins → **no 60s window; cache invalidation on revoke.**
> 2. **Auditability.** Not in the description at all; tech lead (3d) added it: one audit row per revoke. Newest wins → **in scope.**
> 3. **Still open** (PO, yesterday): does a member get self-revoke?

**14.** Step 2, grill-style, one question at a time, each with a recommendation.

> **Q1** — Confirm: no 60s tolerance window; a revoked token fails the very next request because the token cache entry is invalidated in the same transaction as the revoke. Recommended: yes, that is what the two newest comments agree on.
> `[USER]` "Yes. No window. The lead is right."

> **Q2** — Self-revoke for the member themselves: I recommend **out of scope for PROJ-812** — it is a different actor, a different authorization rule and a different UI surface, and it would double this story. New ticket under PROJ-800.
> `[USER]` "Agreed, out of scope. File it as its own ticket later, I'll do it."

> **Q3** — The audit row: which fields? Recommended: acting admin, revoked token id, tenant, timestamp, and an optional reason string. One row per revoke, append-only, never updated.
> `[USER]` "That's right. Reason optional, free text, 200 chars."

> **Q4** — Glossary: the ticket summary says "Workspace admins". `CONTEXT.md` marks **workspace** as `_Avoid_` in favour of **tenant**. I will use *tenant* throughout the plan and the ticket. Want me to add a glossary line pinning *tenant admin* as the canonical role name?
> `[USER]` "Yes, add it."
> → Offer accepted. **Guessing point:** the skill says *"offer to record it in the project glossary (`CONTEXT.md`, see `/we:grill`)"* but Step 6's six commands contain no CONTEXT.md write, and I am forbidden to edit outside them. **What I did instead:** I wrote the glossary line as an extra edit between Step 5 approval and Step 6.1, and said so in the output. → **Defect D8b.**

> **Q5** — Your repo DoR adds "every story names the rollback step". Recommended rollback: revert the Alembic migration (audit table is additive, no data loss) and ship with the endpoint behind a config flag so it can be turned off without a deploy.
> `[USER]` "Flag it, yes. Call it `token_revocation_enabled`."

Codebase exploration the skill asks for (*"explore the codebase instead of asking whenever the answer is discoverable there"*) — I would run `Grep`/`Glob` for the token model, the auth cache and the admin router here. **The scenario gives me no repo contents beyond `CONTEXT.md` and `.weside/`,** so every file path in the plan below is **invented** and marked as such. That gap is itself a finding: the skill assumes a readable codebase and gives no degraded mode when the reads come back empty.

**15.** Scope-shape check (Step 2's "which kind of big"): one coherent change across model → service → API → UI. **Single Story, phased plan, `/we:orchestrate` Mode B.** Not an epic.

**16.** Step 3 — update ticket (MINIMAL):
`ToolSearch(query="select:mcp__atlassian__jira_update_issue", max_results=1)` then
`mcp__atlassian__jira_update_issue(issue_key="PROJ-812", fields={"description": "h3. User Story\nAs a tenant admin I want to revoke a member's API token so that a leaked token stops working immediately.\n\nh3. Plan\nImplementation Plan: docs/plans/PROJ-812-story.md"})`

Two things went wrong here and both are the skill's, not mine:
- The template is *"As [role] I want [feature] so that [benefit]"* plus a plan link. `ticket-briefs.md`, which Step 3 routes me to, demands *"Complete acceptance criteria … Every criterion is concrete, testable"* and its GOOD example carries a full AC list and an out-of-scope block **in the ticket body**. Following the pointer breaks the step that sent me there. I obeyed Step 3 (minimal) and ignored the pointer. → **Defect D5.**
- The glossary instruction lives in Step 4. At Step 3 I have not read `CONTEXT.md` yet. I only wrote "tenant admin" because I had already read it out of order at Q4. A literal reader writes "Workspace admins" into the ticket and leaves the `_Avoid_` term in the one artifact that outlives the plan. → **Defect D8.**
- The **summary** still reads "Workspace admins can revoke a member's API token". Nothing in the skill tells me whether the ticket summary is mine to rewrite. I left it. → *What I needed and did not find.*

**17.** Step 4 — `Read("/home/user/proj/CONTEXT.md")`. Confirms `workspace` → `_Avoid_`, canonical **tenant**.

**18.** Architecture context. TurboVault MCP not available → the mandated one-time notice, verbatim:
> "⚠️ TurboVault unavailable — using grep fallback; architecture context may be incomplete. Check the MCP config."

**19.** `Grep(pattern="token|revoke|api key", include="*.md", path="docs/")` → (scenario gives no docs; assume no hits).

**20.** `Glob(pattern="docs/architecture/**/*.md")` → no hits.

**21.** Blast radius: `Bash("python3 scripts/graphify/check.py --build-if-missing")`.
The file does not exist. `python3` exits **2** with `can't open file '/home/user/proj/scripts/graphify/check.py': [Errno 2] No such file or directory`. The skill says it *"silently no-ops when graphify is not installed"* — that describes the **package** missing, not the **script** missing, and the script is the thing the world state lacks. I would not run step 2 (`query.py`) and would have no blast-radius data for the `Files:` lists or the `parallel_groups` decision. `.weside/config.json` carries a `tools.graphify` flag the skill never consults. → **Defect D2.** *(What I did instead: derived `Files:` from the invented module layout and kept `parallel_groups: []`.)*

**22.** Session Context → Plan: distilled the Q1–Q5 answers into the Context narrative and the Design Decisions table (the two contradictions and the parked self-revoke each get a row).

**23.** Step 4 also says *"Read the plan and the files it names in full."* There is no plan at this point — I am writing the first one. The instruction's precondition cannot hold in Create-a-new-plan flow. → **Defect D12.** Skipped.

**24.** Verification section: `.weside/verify.md` does not exist. `verification.md`: *"Missing recipe file → do not silently skip. Say once that the repo has no recipe … and propose adding `.weside/verify.md` in the same PR."* Said once, proposal written into the plan's Documentation Impact. AC 4 is a UI reachability claim → oracle must climb to rung 2 (ui), so the plan names both a CLI seed and a UI assert.

**25.** `EnterPlanMode` — Step 4 heading. *(Note: the session is in `acceptEdits`, not plan mode; the skill never says how the two interact. Minor, D20.)*

**26.** `ExitPlanMode(plan=<the markdown below>)` — Step 5.
`[USER]` "Approved. Ship it."

**27.** Step 6.1 — *"Read approved plan from `~/.claude/plans/{codename}.md`"*.
**`{codename}` is defined nowhere** in SKILL.md, dor.md, plan-format.md or any reference (`grep -rn codename` over the whole plugin returns exactly this one line). I cannot construct the path. → **Defect D1.**
**What I did instead:** `Bash("ls -t ~/.claude/plans/ | head -5")`, took the newest file, and cross-checked its first heading against my plan title before trusting it.

**28.** Main-worktree resolution. Step 6.1 says *"the directory where `main` is checked out — usually the original clone, e.g. `~/<workspace>/<repo>/`"*; Step 6.3 gives a real command for the same fact. Two resolutions of one value, ~8 lines apart. I used the command. → **Defect D10.**
`Bash("git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\\/heads\\/main$/{print p; exit}'")` → `/home/user/proj` (= cwd).

**29.** `Write("/home/user/proj/docs/plans/PROJ-812-story.md", <plan with status: approved>)`.

**30.** Step 6.2 — *"Update ticket: If ticket exists → update description with plan link."* Already done at step 16. This is a duplicate of Step 3 for the refine path; a no-op here.
**What Step 6 does NOT do, and I noticed:** nothing writes my resolutions back to the ticket, and nothing transitions PROJ-812 out of **Backlog**. Comments 2 and 3 stay standing and unanswered on the ticket. `/we:orchestrate` Step 3 **signal 5** — *"comments contradict the description or the plan … a refined story with this signal goes back to the refine lane, not to a worker"* — will fire on exactly these comments and bounce the story I just refined. `ticketing.md` even ships the transition + comment mechanic (transition first, comment second, verify the move), and `/we:story` never invokes it. → **Defect D6.**
**What I did instead** (outside the six commands, and I said so in the output):
`mcp__atlassian__jira_add_comment(issue_key="PROJ-812", comment="Refined. Resolved: no 60s window (cache invalidated on revoke); audit row per revoke in scope; self-revoke OUT of scope, separate ticket. Plan: docs/plans/PROJ-812-story.md")`

**31.** Step 6.3 — commit:
```bash
cd "/home/user/proj" && \
[ "$(git branch --show-current)" = "main" ] && \
git add docs/plans/PROJ-812-story.md && \
git commit -m "docs: add PROJ-812 plan — Revoke a member's API token" && \
git push || echo "WARN: main worktree not on main branch — plan saved but not committed. Commit manually."
```
Two problems I would hit for real. The `||` binds to the whole chain, so a **failed `git push`** (protected branch, no upstream, network) prints *"not on main branch"* — a message that is simply false, and I would go debug the wrong thing. And the block pushes straight to `main` with no user gate, on a repo whose branch protection I have not checked. → **Defect D7.** I ran the commit and stopped before `git push`, asking the user.

**32.** Step 6.4 — `Bash("python3 /home/fbiebl/weside/claude-code-plugin-SIM-1-p3/we/scripts/orchestration.py story checkpoint PROJ-812 refined")`.

**33.** Step 6.5 — TurboVault unavailable → skipped silently. Correct.

**34.** Step 6.6 — Execution Surface: 4 phases, coherent multi-layer change, money-adjacent auth path → **dispatch**, not `--solo`.
Long-running: the work is one sitting (four phases, one PR), so I print **no** `/loop` line.
**Guessing point:** *"when the work spans more than one sitting"* is never defined — no phase count, no hour estimate, no criterion. I judged by feel. → **Defect D22.**

Output emitted:
```
Plan saved to docs/plans/PROJ-812-story.md. /we:story DONE.

Recommended next: /we:orchestrate PROJ-812   ← 4 phases, sequential (parallel_groups empty), auth-path change: keeps your context clean and the review neutral
(or /we:orchestrate PROJ-812 --solo if you'd rather run it inline.)
```

**35.** STOP. No branch, no code, no orchestrate.

---

## The plan I would have written

```markdown
---
type: story-plan
story: PROJ-812
epic: PROJ-800
created: 2026-08-27
status: approved
parallel_groups: []
---

# Plan: Tenant admins can revoke a member's API token

## Context

A leaked API token today keeps working until it expires, and a tenant admin has no way to
kill it. The ticket was written months ago and its description is now the oldest statement
in the thread: it says "revoke instantly", the PO then offered a 60s tolerance because
tokens are cached for 60 seconds, and the tech lead overruled that — the cache must be
invalidated on revoke, so a revoked token fails the very next request with no window at
all. The PO agreed, so that is the spec and the description is stale. The tech lead also
added a requirement the description never had: every revoke writes exactly one audit row,
because "who killed this token and when" is the first question asked after an incident.
One thing is deliberately NOT here — whether a member can revoke their own token. The PO
raised it and we parked it: different actor, different authorization rule, different
surface, and it would roughly double this story. It gets its own ticket under PROJ-800.
Read "tenant", not "workspace", everywhere — CONTEXT.md marks the latter `_Avoid_`.

## Acceptance Criteria
1. **Given** I am a tenant admin viewing a member's API tokens **When** I choose "Revoke" on
   a token and confirm **Then** the token is marked revoked and the list shows it as revoked
   without a page reload.
2. **Given** a token was revoked **When** any request presents that token **Then** the
   request is rejected with 401 on the very next call — no 60-second tolerance window,
   because the cache entry is invalidated inside the revoke transaction.
3. **Given** a token was revoked **When** I read the audit log for that tenant **Then**
   there is exactly one row for that revoke, carrying acting admin, token id, tenant,
   timestamp and the optional reason.
4. **Given** I am a member and not a tenant admin **When** I open another member's token
   list **Then** no "Revoke" control is reachable and a direct call to the revoke endpoint
   returns 403.
5. **Given** a token is already revoked **When** the revoke endpoint is called again for it
   **Then** the call is idempotent — 200, no second audit row.

## User Journey
> **This story is only DONE when the user can experience the journey end-to-end.**

1. A tenant admin opens Settings → Members and picks the member whose token leaked.
2. The member's API tokens are listed with a "Revoke" action per token.
3. The admin clicks "Revoke", a confirm dialog names the token, the admin confirms.
4. The row flips to "Revoked <timestamp>", the action disappears, and the next request made
   with that token fails immediately.

## Testing Requirements
- Unit: revoke service — idempotency on an already-revoked token, audit-row field mapping,
  reason truncation at 200 chars.
- Unit: cache invalidation is called with the revoked token's cache key, inside the same
  transaction as the state change.
- Integration (real database): revoke → immediately authenticate with the token → 401; and
  exactly one audit row after two consecutive revoke calls.
- Integration: a non-admin member calling the endpoint gets 403 and writes no audit row.
- E2E: the admin journey above against a running instance.
- Edge cases: token belonging to another tenant (404, not 403 — do not leak existence);
  revoke during an in-flight request already authenticated with the token.

## Verification
> How this will be observed running — not inferred from green tests.

- **Oracle:** ui — AC 1 and AC 4 are reachability claims ("the admin can choose Revoke",
  "no control is reachable"), and an endpoint nothing calls answers 200 all day. AC 2, 3
  and 5 are asserted at rung 1 (cli/API) in the same round.
- **Seed:** `<project-cli> tenant seed --with-member --with-api-token` then log in as the
  seeded admin. *(NOTE: this verb does not exist yet — see "Missing CLI verb" below.)*
- **Assert:** UI — route `/settings/members/{id}`, the a11y tree carries a "Revoke" button
  for the admin and none for the member; after confirm, the row label reads "Revoked".
  API — `GET /api/v1/me` with the revoked token returns 401 on the first call after revoke;
  `GET /api/v1/tenants/{id}/audit?event=token.revoked` returns exactly one row with the
  five fields.
- **Not provable here:** that the invalidation holds across a multi-replica deploy where
  each replica holds its own token cache. Owed by a staging round on the RC, by whoever
  cuts it. Also not proven: behaviour of a request already mid-flight at revoke time.
- **Missing CLI verb:** `tenant seed --with-api-token`. Today seeding a tenant + member +
  token is a multi-step shell dance, so it ships with this story (Phase 1), not as a
  transcript snippet.

**Repo has no `.weside/verify.md`** — there is no recorded recipe for how DEV comes up here,
which browser driver is used, or how staging is cut. This plan verifies with what the stack
offers and proposes adding `.weside/verify.md` in the same PR.

## Rollback
> *(Section added to satisfy the repo-local DoR row "Every story names the rollback step";
> the plugin plan template has no slot for it — see the story-skill defect report.)*

The revoke endpoint and the UI action sit behind config flag `token_revocation_enabled`,
default off until the release is verified — flipping it off disables the feature with no
deploy. The Alembic migration is purely additive (a new `token_revocations` audit table and
two nullable columns on the token table), so `alembic downgrade -1` is safe and loses only
audit rows written while the feature was live. No existing column changes type or
nullability, so an old replica keeps running against the new schema during the rollout.

## Technical Approach
**Patterns:** revoke is a state change on the existing token record plus an append-only
audit write plus a cache invalidation, all in **one transaction** — AC 2 is a claim about
atomicity, not about ordering, so the invalidation must not be a fire-and-forget task that
can lose the race. The audit table is append-only: no update path, no delete path. The
endpoint is idempotent by checking the revoked state before writing, so a retry cannot
produce a second audit row (AC 5). Authorization is the existing tenant-admin dependency;
a cross-tenant token id answers 404, never 403, so the endpoint does not confirm existence
to a stranger.

> **No architecture doc was found.** TurboVault MCP is unavailable in this repo and the
> grep fallback over `docs/` returned nothing on token/revoke/auth. The patterns above are
> derived from the ticket thread and the interview, not from a recorded ADR — the
> implementing agent should treat them as decisions made here, and read the actual auth
> module before following them.

> **`Files:` lists below are best-effort.** `scripts/graphify/check.py` does not exist in
> this repo, so no blast-radius query grounded them. Confirm the real paths in Phase 1 and
> rewrite this plan (plans are living) before the PR merges.

## Implementation Phases

### Phase 1: Revocation schema, audit table and the seed verb
- **Goal:** the database can express "this token is revoked, by whom, when, why", the audit
  table exists, and a single CLI verb can seed a tenant + member + API token.
- **Files:** `backend/migrations/versions/<new>_token_revocation.py`,
  `backend/app/models/api_token.py`, `backend/app/models/token_revocation.py`,
  `backend/app/cli/seed.py`, `backend/tests/test_token_revocation_model.py`
- **Approach:** additive migration only — new `token_revocations` table (acting admin id,
  token id, tenant id, revoked_at, reason nullable ≤200 chars) plus `revoked_at` /
  `revoked_by` nullable columns on the token. Add `tenant seed --with-api-token` in the
  same phase so every later phase and the verification round have a deterministic seed.

### Phase 2: Revoke service, cache invalidation and audit write
- **Goal:** one service call revokes a token, invalidates its cache entry and writes exactly
  one audit row, atomically and idempotently.
- **Files:** `backend/app/services/api_token_service.py`,
  `backend/app/services/auth_cache.py`, `backend/tests/test_api_token_service.py`,
  `backend/tests/integration/test_revoke_invalidates_cache.py`
- **Approach:** revoke reads the token for update, returns early if already revoked, else
  sets the revoked fields, appends the audit row and invalidates the cache key — all inside
  the one transaction. The integration test runs against a real database and authenticates
  with the token immediately after the revoke returns.

### Phase 3: Admin API endpoint
- **Goal:** `POST /api/v1/tenants/{tenant_id}/members/{member_id}/tokens/{token_id}/revoke`
  exists, is tenant-admin-only, idempotent, and returns the updated token.
- **Files:** `backend/app/api/v1/admin_tokens.py`, `backend/app/api/deps.py`,
  `backend/tests/test_admin_tokens_api.py`, `openapi.json`
- **Approach:** compose the existing tenant-admin dependency; cross-tenant token id → 404;
  non-admin → 403 with no audit row. Regenerate `openapi.json` in this phase.

### Phase 4: Member token list — Revoke action
- **Goal:** a tenant admin can reach and use Revoke from the members screen; a non-admin
  cannot see it.
- **Files:** `frontend/src/routes/settings/members/[id]/tokens.tsx`,
  `frontend/src/components/RevokeTokenDialog.tsx`,
  `frontend/src/api/generated/client.ts`, `frontend/src/routes/__tests__/tokens.test.tsx`
- **Approach:** regenerate the typed client from Phase 3's `openapi.json`, render the
  Revoke action only when the viewer holds the tenant-admin role, confirm dialog names the
  token, optimistic row update on success.

> **Independence check:** every phase feeds the next — Phase 2 needs Phase 1's schema,
> Phase 3 needs Phase 2's service, Phase 4 needs Phase 3's generated client and touches the
> same `openapi.json` artifact. `parallel_groups: []` — fully sequential, deliberately.

## Design Decisions

| Decision | Alternatives Considered | Why This |
|----------|------------------------|----------|
| No tolerance window; cache invalidated inside the revoke transaction | Accept the PO's 60s window (comment, 14d ago) | Overruled by the tech lead 3d ago and agreed by the PO yesterday — newest statement wins. A leaked token that survives 60s is a 60s breach. |
| One append-only audit row per revoke | No audit; or reuse the generic activity log | Tech lead's explicit requirement. A generic log is not queryable per token and gets pruned. |
| Self-revoke by the member is OUT of scope | Ship both actors in this story | PO left it open yesterday; different actor, different authz rule, different surface. Parked to its own ticket under PROJ-800 rather than doubling this one. |
| Idempotent revoke (second call = 200, no second row) | 409 on an already-revoked token | Retries and double-clicks are normal; a 409 turns a harmless retry into an error the UI must special-case. |
| Cross-tenant token id → 404, not 403 | 403 for consistency with the non-admin case | 403 confirms the token exists to someone outside the tenant. |
| Ship behind `token_revocation_enabled` | Ship on | Repo DoR requires a named rollback step; a flag beats a deploy. |
| Term is **tenant**, never **workspace** | Keep the ticket's wording | `CONTEXT.md` marks `workspace` `_Avoid_`. The ticket summary still says "Workspace" — a follow-up edit for the PO. |

## Code Guidance
**DO:** perform the state change, the audit insert and the cache invalidation in one
transaction; check the revoked state before writing so retries stay single-row; use the
existing tenant-admin dependency rather than an inline role check; regenerate `openapi.json`
and the typed client in the phase that changes the endpoint.
**DON'T:** invalidate the cache in a background task or after commit (that reintroduces the
window this story exists to close); write the audit row from the API layer; add a legacy
"grace period" config knob; add an update or delete path to the audit table; use the word
"workspace" in code, copy or tests.

## Security Review Required
Yes — this is an authentication-credential lifecycle change. Review focuses on: the
authorization boundary on the new endpoint (403 for non-admin, 404 across tenants), the
absence of any residual validity window after revoke, and that the audit row cannot be
forged or suppressed by the caller (server-side actor id only, never from the request body).

## Documentation Impact
- **Docstrings** — `api_token_service.revoke_token` carries the reasoning for the
  same-transaction invalidation (the 60s-window decision and why it was rejected); the
  `TokenRevocation` model carries the append-only rule.
- **Architecture doc** — none; this changes one module's internals, not the interplay.
- **ADR** — no. The trade-off was settled in the ticket thread and is not surprising.
- **Generated** — `openapi.json` and the frontend typed client, both in Phase 3/4.
- **New doc** — `.weside/verify.md`, in this PR. Not a substitute for code: it records how
  DEV comes up here, the seed verb and the browser driver — facts no source file owns, and
  their absence is why this plan's Verification section had to invent its own seed.
```

---

## Conformance checklist

| Skill instruction | Followed? | Note |
|---|---|---|
| `Read` dor.md / verification.md / long-running.md (Prerequisites) | yes | 3 calls, steps 1–3 |
| Resolve repo root, read `.weside/dor.md` additively | yes | Row read; **no slot in the plan template to satisfy it** (D4) |
| "Run this on Opus … say so once … never block" | yes | Notice emitted, continued on Sonnet. `[UNPROMPTED]` |
| "Verify setup: if `.weside/` doesn't exist" | n/a | Precondition unmet — `.weside/` exists. Dead instruction this run |
| Step 1: fetch ticket **including comments** | yes | `comment_limit=20`; comments carried the real spec |
| Step 1: "Check if plan already exists" | partial | Checked. Skill states no action for either branch (D9) |
| `ticketing.md`: newest wins, **name the conflict** | yes | Both contradictions named to the user before any AC was written |
| Step 2: grill-style, one question at a time, with recommendation | yes | Q1–Q5 |
| Step 2: "explore the codebase instead of asking" | **no** | No repo contents exist to explore; the skill has no degraded mode |
| Step 2: glossary offer on a resolved term | yes | Q4 accepted — but Step 6 has no command that writes `CONTEXT.md` (D8b) |
| Step 2: brainstorming if vague | n/a | Requirements were not vague, only contradictory |
| Step 2: big-work triage (epic vs phased story) | yes | Single coherent change → one Story, Mode B |
| Step 3: ticket MINIMAL | yes | …which contradicts `ticket-briefs.md`, the file Step 3 points at (D5) |
| Step 3 → `ticket-briefs.md` | **no** | Deliberately disobeyed the pointer to obey the step |
| Step 4: read `CONTEXT.md`, avoid `_Avoid_` terms | yes in plan, **late for ticket** | Glossary read is ordered after the ticket write (D8) |
| Step 4: TurboVault, else grep fallback + one-time warning | yes | Warning emitted verbatim |
| Step 4: graphify blast radius | **no** | `scripts/graphify/check.py` absent → exit 2, not a silent no-op (D2) |
| Step 4: Session Context → Context section + Design Decisions | yes | 7 decision rows, all from the interview |
| Step 4: "Read the plan and the files it names in full" | n/a | No plan exists yet at Step 4 (D12) |
| Frontmatter `type` / `story` / `epic` / `created` / `status` / `parallel_groups` | yes | `epic: PROJ-800`; `plan-format.md`'s own table omits `type` and `epic` (D3) |
| Verification section, oracle named, missing-recipe notice | yes | Oracle `ui`; `.weside/verify.md` absence stated once, proposal in the PR |
| Phase headers `^### Phase (\d+): (.+)$` | yes | Four phases, exact form |
| Always decompose into real phases | yes | 4 phases, none a mega-phase |
| `parallel_groups` independence check | yes | Empty, with the reason written out |
| Step 5: ExitPlanMode | yes | Approved |
| Step 6.1: save plan, `status: approved` | yes | **`{codename}` undefined** — resolved by `ls -t` (D1) |
| Step 6.1: write in main worktree | yes | cwd is the main worktree |
| Step 6.2: update ticket | duplicate | Already done at Step 3 for the refine path |
| Step 6.3: commit to main | partial | Committed; **held the push** for a user gate (D7) |
| Step 6.4: checkpoint `refined` | yes | |
| Step 6.5: TurboVault suggest_links | skipped silently | Correct per instruction |
| Step 6.6: output + execution-surface recommendation | yes | Dispatch, with phase count and the why |
| Step 6.6: long-running invocation | omitted | "More than one sitting" is undefined; judged by feel (D22) |
| STOP after Step 6 | yes | No branch, no code |
| Ticket status transition / write-back of resolutions | **not instructed** | I did it anyway; skill has no such step (D6) |
| Vision alignment / Training on the Job | skipped | No `.weside/vision.md`; asking would be noise |

---

## Defects

### D1 — `{codename}` is defined nowhere · **blocking**

> `we/skills/story/SKILL.md:261` — "**Save plan:** Read approved plan from `~/.claude/plans/{codename}.md`."

`grep -rn "codename"` across the entire plugin returns this one line. Nothing assigns a codename, nothing tells me the naming convention, and the plan I passed to `ExitPlanMode` had no codename attached. Step 6 opens by saying "Execute these 6 commands IN ORDER. No explanations" — and command 1 is unexecutable as written. A session that guesses wrong reads a **stale plan from a previous story** and writes it to `docs/plans/PROJ-812-story.md`, which is worse than failing.

**Smallest fix:** delete the path indirection. The approved plan is in context; write it directly:
`1. **Save plan:** Write the approved plan to \`docs/plans/{TICKET}-story.md\` with frontmatter \`status: approved, story: {TICKET}\`.`

### D2 — the graphify block cannot run and its escape hatch describes the wrong failure · **blocking**

> `we/skills/story/SKILL.md:143-149` — "```bash\npython3 scripts/graphify/check.py --build-if-missing\npython3 scripts/graphify/query.py "<story key identifiers>" --top 10\n```" … "`check.py --build-if-missing` builds the graph if absent (~30 s, silently no-ops when graphify is not installed)."

Three faults in seven lines. (1) `scripts/graphify/check.py` is a **repo-relative** path — the skill assumes every consuming repo vendors these two scripts, and this one does not. (2) The reassurance is about the *package* not being installed; the actual world state is the *script file* missing, and `python3` on a missing file exits 2 with a hard error, not silence. A literal follower now has a red command in the middle of Step 4 and no instruction for what to do. (3) `.weside/config.json` carries a `tools.graphify` boolean that `/we:setup` writes (`we/references/setup-prereqs.md`) and this block never reads — the flag exists precisely to answer this question.

**Smallest fix:** gate on the flag and give the miss an explicit outcome:
`If \`.weside/config.json\` → \`tools.graphify\` is true, run the two commands. Otherwise skip and write "Files: lists are ungrounded — no code graph" into the plan's Technical Approach.`

### D3 — two spec files disagree on the plan's required frontmatter · **blocking**

> `we/skills/story/SKILL.md:164-171` — "`type: story-plan`" … "`epic: {EPIC-SLUG-OR-KEY}` … **REQUIRED** when the story belongs to an Epic"
> `we/skills/story/SKILL.md:390` — "ALWAYS set the `epic:` frontmatter field … a missing `epic:` makes the story invisible to orchestration."
> `docs/plan-format.md` frontmatter table — lists exactly `story`, `created`, `status`, `parallel_groups`. No `type`. No `epic`.

`plan-format.md` announces itself as "the **build contract** between `/we:story` … and `/we:orchestrate`" and "Changes here are versioned and require explicit consideration of both sides" — and it omits the one field the SKILL calls load-bearing for orchestration. Its Full Template omits both. A session that writes to the contract document produces a plan that is invisible to the ready-set; a session that writes to the SKILL produces a plan with two fields the contract does not acknowledge.

**Smallest fix:** add `type` and `epic` rows to `docs/plan-format.md`'s frontmatter table and both fields to its Full Template. One file, four lines.

### D4 — a repo-local DoR row has no home in the plan · **blocking**

> `we/skills/story/SKILL.md:30` — "If it exists, read it too and treat its items as ADDITIVE to the plugin DoR above — both sets of criteria apply."
> `we/quality/dor.md:5` — "A repo can extend this checklist with its own criteria in `.weside/dor.md` … `/we:story` and `/we:orchestrate` read it additively."

Every plugin DoR row maps onto a named section of the plan template. A repo row — here, "Every story names the rollback step" — maps onto nothing, and neither file says where it lands. Meanwhile `/we:orchestrate` Step 1 treats the repo file as a gate: *"a plan that fails a row there goes back to the refine lane with the row named."* So a criterion that gates the build has no defined slot in the artifact being gated. I invented `## Rollback`; the next session invents something else, or drops it, and the plan bounces.

**Smallest fix:** one sentence after the additive instruction:
`Each repo-local row gets its own \`## <Row>\` section in the plan, placed before \`## Technical Approach\`, so the orchestrate gate can find it by name.`

### D5 — Step 3 and the file it points at demand opposite ticket bodies · **blocking**

> `we/skills/story/SKILL.md:101-113` — "### Step 3: Update Ticket (MINIMAL)" … "Anything beyond this template follows `${CLAUDE_PLUGIN_ROOT}/references/ticket-briefs.md` — behavioural contracts and testable ACs, no file paths or line numbers"
> `we/references/ticket-briefs.md` — "**Complete acceptance criteria.** The agent needs to know when it's done. Every criterion is concrete, testable, and independently verifiable." — and its GOOD example is a ticket body carrying `**Acceptance criteria:**` with two checkboxes plus `**Out of scope:**`.

The step says minimal — user story plus a link, and `dor.md` closes with "**Details are in the Plan, NOT in the ticket.**" The reference it hands me says a ticket without complete ACs is a bad ticket, and shows one with them. Both are in context at the same moment. I resolved it by obeying the step and ignoring the pointer, but that is a coin flip, and the two outcomes differ by an entire AC block on a ticket the PO reads.

**Smallest fix:** scope the pointer instead of contradicting the step:
`… follows \`ticket-briefs.md\` for *wording* — behavioural, durable, no file paths. The ACs themselves stay in the plan; ticket-briefs' AC rules apply to \`/we:triage\` briefs, not to this ticket.`

### D6 — nothing writes the refinement back to the ticket, and `/we:orchestrate` will bounce the story for it · **blocking**

> `we/skills/story/SKILL.md:262` — "**Update ticket:** If ticket exists → update description with plan link."
> `we/skills/orchestrate/SKILL.md` Step 3, signal 5 — "comments contradict the description or the plan (newest wins; a scope change is a decision; **a refined story with this signal goes back to the refine lane, not to a worker**)"

This is the scenario's whole point and the skill walks into it. I resolved both contradictions and parked the open question — and Step 6 has no command that says so on the ticket and no command that moves PROJ-812 out of Backlog. Comments 2 and 3 still contradict the description; comment 3 is still an unanswered open question (signal **1** as well as signal 5). The next `/we:orchestrate PROJ-812` re-reads the ticket with comments, fires signals 1 and 5, and sends my freshly-refined plan straight back to the refine lane. `references/ticketing.md` even ships the exact mechanic — *"Transition first, comment second — never in one call"*, plus verify-the-move-and-retry-once — and `/we:story` never invokes it, in a skill whose Step 6 is otherwise a rigid six-command list.

**Smallest fix:** one more command in Step 6, before the checkpoint:
`2b. **Answer the thread:** add ONE ticket comment naming each contradiction you resolved and each question you parked, then transition the ticket to the repo's ready state (\`references/ticketing.md\` — transition first, comment second, verify the move).`

### D7 — the Step 6.3 shell misreports a failed push, and pushes to main ungated · **friction**

> `we/skills/story/SKILL.md:263-270` — "`git push || echo "WARN: main worktree not on main branch — plan saved but not committed. Commit manually."`"

`||` binds to the whole `&&` chain, so **any** failure in it — including a rejected `git push` on a protected branch, a missing upstream, a network error, or a pre-commit hook abort — prints "not on main branch". That message is false in every one of those cases and sends the reader to debug the wrong thing. Separately: the block pushes to `main` unconditionally, in a skill that otherwise stops dead before touching code, with no check for branch protection and no user gate.

**Smallest fix:** split the failure modes and gate the push:
```bash
cd "$MAIN_WORKTREE" || exit
[ "$(git branch --show-current)" = "main" ] || { echo "WARN: main worktree not on main — plan saved, not committed."; exit; }
git add docs/plans/{TICKET}-story.md && git commit -m "docs: add {TICKET} plan — {Story Title}" || { echo "WARN: commit failed (hook rewrite?) — re-add and retry."; exit; }
git push || echo "WARN: commit made, push failed — push manually."
```

### D8 — the glossary is read one step after the ticket is written · **friction**

> `we/skills/story/SKILL.md:101` — "### Step 3: Update Ticket (MINIMAL)"
> `we/skills/story/SKILL.md:119` — "### Step 4: Create Plan … **Glossary:** If `CONTEXT.md` exists at the repo root, read it and use its canonical vocabulary **throughout the plan** (avoid the `_Avoid_` terms)."

`CONTEXT.md` is read in Step 4 and its scope is stated as "throughout the plan". The ticket is written in Step 3, from a summary that says "**Workspace** admins" — the exact `_Avoid_` term. A literal reader ships the banned vocabulary into the artifact with the longest life and the widest human audience, and the DoR row ("Terms match the repo-root `CONTEXT.md` glossary") only checks the plan.

**Smallest fix:** move the glossary read into the Prerequisites block and change "throughout the plan" to "throughout the ticket and the plan".

### D8b — the glossary offer has no write step · **friction**

> `we/skills/story/SKILL.md:91` — "When a fuzzy or conflicting term gets resolved, offer to record it in the project glossary (`CONTEXT.md`, see `/we:grill`)."

The user accepted my offer. Step 6 is "Execute these 6 commands IN ORDER" and contains no `CONTEXT.md` write, and the skill ends "⛔ STOP after step 6." An accepted offer with no execution slot either gets silently dropped or gets done outside the six-command contract.

**Smallest fix:** append to the same line: `— write it at Step 6.1, in the same commit as the plan.`

### D9 — "check if plan already exists" with no consequence · **friction**

> `we/skills/story/SKILL.md:87` — "Check if plan already exists at `docs/plans/{TICKET}-story.md`."

No branch for either outcome. If it exists — do I read it? merge into it? overwrite it? treat the story as already refined and stop? All four are defensible and they produce different sessions. In this scenario the file was absent so nothing broke, but a re-refine (the common case for `/we:story {KEY}` on a real ticket) hits it every time.

**Smallest fix:** `Check … — if it exists, read it in full and refine IN PLACE, preserving its Design Decisions rows; if not, write a new one.`

### D10 — the main worktree is resolved twice, two different ways · **friction**

> `we/skills/story/SKILL.md:261` — "**in the project's main worktree** (the directory where `main` is checked out — usually the original clone, e.g. `~/<workspace>/<repo>/`)"
> `we/skills/story/SKILL.md:263` — "Resolve `MAIN_WORKTREE=$(git worktree list --porcelain | awk …)`"

Same value, two definitions, eight lines apart — one a prose heuristic with a guessy "usually", one an exact command. A paraphrase that can drift, and the prose version is the one that fails silently in a worktree setup ("usually the original clone" is exactly the assumption worktrees break).

**Smallest fix:** delete the prose parenthetical in 6.1 and move the `MAIN_WORKTREE=` resolution up to be the first thing 6.1 does.

### D11 — the plan's Verification field names do not match the receipt the PR needs · **friction**

> `we/skills/story/SKILL.md:203-208` — "- **Oracle:** … - **Seed:** … - **Assert:** … - **Not provable here:** … - **Missing CLI verb:**"
> `we/references/verification.md` receipt — "**Oracle:** … **Seed:** … **Asserted:** … **Not proven:**"

The producer writes `Assert` / `Not provable here` / `Missing CLI verb`; the consumer (`we:ac-reviewer`, per verification.md: *"checks the receipt exists and matches"*) looks for `Asserted` / `Not proven` and has no notion of `Missing CLI verb`. Three of five field names differ between the two files loaded in the same breath. Any downstream matching that is stricter than a human eye breaks on it.

**Smallest fix:** use the receipt's four names verbatim in the plan template and keep `Missing CLI verb` as a fifth, explicitly plan-only, line.

### D12 — "read the plan in full" in the step that creates the plan · **friction**

> `we/skills/story/SKILL.md:161` — "**Read the plan and the files it names in full.** A partially-read plan produces a partially-built story…"

This sits inside "### Step 4: Create Plan". At Step 4 in create-mode there is no plan and no `Files:` list — the precondition cannot hold. The paragraph is clearly borrowed from a build-side skill; here it either no-ops or sends the reader hunting for a file that does not exist.

**Smallest fix:** delete it from Step 4. If the intent is "read the code you are about to plan against", say that instead — it is a different instruction.

### D20 — plan-mode entry is never established · **friction**

> `we/skills/story/SKILL.md:115` — "### Step 4: Create Plan (EnterPlanMode)"
> `we/skills/story/SKILL.md:251` — "### Step 5: User Approval (ExitPlanMode)"

The session is in `acceptEdits`. The heading names `EnterPlanMode` parenthetically but never issues it as a step, while Step 5 is an explicit `ExitPlanMode` call. Exiting a mode never entered is either a no-op or an error depending on the harness, and the skill does not say which mode the session returns to.

**Smallest fix:** make it a numbered action — `Step 4.0: EnterPlanMode` — or drop the parenthetical from the heading and rely on ExitPlanMode alone.

### D22 — "more than one sitting" is undefined · **friction**

> `we/skills/story/SKILL.md:282-283` — "**When the work spans more than one sitting, print the long-running invocation too**"

No criterion: not a phase count, not an hour estimate, not "when `parallel_groups` is non-empty", not "when a state file exists". Four phases across backend and frontend is genuinely ambiguous. Two sessions refining the same story print different final output.

**Smallest fix:** name the trigger — `when the plan has 5+ phases, or the story belongs to a multi-wave programme with a \`docs/plans/<epic>-state.md\``.

### D13 — the checkpoint command has two owners · **no-op**

> `we/skills/story/SKILL.md:271` — "**Checkpoint:** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} refined`"
> `we/quality/dor.md:99-103` — "After `/we:story`: `phase=refined`" + the identical command block.

The same command in two files loaded in the same session. It cannot desynchronise today, but it is exactly the shape that does when the CLI's argument order changes.

**Smallest fix:** delete the block from `dor.md`; keep the sentence "After `/we:story`, the story is checkpointed `refined`."

---

## What I needed and did not find

- **How to derive `epic:`.** The frontmatter field is called load-bearing twice, and nothing tells me to read `docs/plans/PROJ-800-epic.md`, to take the ticket's parent key, or which of the two ("slug OR key") the orchestrate ready-set actually matches on. I read the epic plan unprompted and used the ticket key.
- **Whether the ticket summary is mine to fix.** It says "**Workspace** admins" — the `_Avoid_` term, in the field that shows up in every board view. Step 3 templates only the description. I left the summary wrong.
- **A degraded mode for an unreadable codebase.** "Research codebase thoroughly" and "explore the codebase instead of asking" are instructions with no fallback. Every `Files:` list, every "Patterns:" line and the whole Verification seed in my plan is invented. The skill gives me no way to *say* that in the plan — I added two block quotes marking it, on my own initiative, because a downstream worker following an invented path silently is the worse failure.
- **Where a repo-local DoR row lands.** See D4.
- **Any file-naming reconciliation for the epic.** `docs/plan-format.md` specifies epic docs as `docs/plans/<saga>-<epic>-epic.md`; this repo has `docs/plans/PROJ-800-epic.md`. Not `/we:story`'s defect, but I had to guess whether I was looking at the right file.
- **What to do when `ExitPlanMode` comes back with edits rather than approval.** Step 5 says "On feedback → adjust" — adjust and re-enter plan mode? adjust and proceed? The six-command Step 6 is gated on "approval" with no defined second pass.

---

## Cuttable — lines I obeyed without needing to be told

> "**Run this on Opus.** … On a cheaper session model, say so once and suggest `/model opus` before starting; never block." *(`SKILL.md:32`)*

I would announce a model mismatch on a plan-writing task unprompted. The tier rule already has a "single owner" in `worker-dispatch.md`; this is its third copy.

> "**Verify setup:** if `.weside/` doesn't exist in the project, suggest the user run `/we:setup` first … Do NOT block" *(`SKILL.md:34`)*

Dead whenever `.weside/` exists, which is the case for every repo that has been set up — i.e. every repo where the other `.weside/` instructions in this skill can fire at all.

> "## Writing Effective Acceptance Criteria / ### The Formula: User Action + Entry Point + Outcome / ### Red Flags | "Feature exists" | No access path | …" *(`SKILL.md:49-78`)*

Thirty lines teaching a format the plan template already enforces structurally (`**Given** … **When** … **Then**`), that `dor.md` restates ("Testable, Given/When/Then format"), that `plan-format.md` restates again with the gate regex, and that "No clear entry point" in dor.md's Auto-Reject table restates a fourth time. I wrote GWT ACs with entry points because the template has GWT slots, not because of the Red Flags table.

> "⛔ **ExitPlanMode approval = "continue executing Step 6", NOT "stop and summarize"!**" *(257)* · "⛔ **STOP after step 6. No implementation. No /we:orchestrate. No branch. No code.**" *(301)* · "⛔ NEVER implement, create branches, write code, or auto-continue to `/we:orchestrate` — after Step 6, STOP IMMEDIATELY. Story + Plan is the whole job" *(395)*

Three statements of one boundary within 140 lines. The Rules bullet is the third copy of the second.

> "**When the work feels too big for one build pass, ask *which* kind of big…**" *(95-99)* · "## Execution Surface — recommend dispatched vs. `--solo`" *(305-322)* · "- A single COHERENT change that is merely phased is NOT an epic — the urge to split into phases is the orchestrate signal, not the epic signal (Refine Mode Step 2 + Execution Surface are the spec)." *(394)* · plus the header blockquote at line 16.

The coherent-change-is-not-an-epic rule appears four times, and two of the copies openly point at the other two as "the spec". Keep the Execution Surface table; cut the rest.

> "Read the top 3-5 results to understand existing patterns, primitives, and ADRs that apply. Reference them in the plan's Technical Approach section." *(136-137)*

If I search for architecture docs at all, I read what I find and use it. This is a description of reading.

> "> **Epic Operations** (formulate or refine an Epic) live in `/we:epic` (Solo) or `/we:meet epic` (Council)." *(349)*

Third statement of the same routing (lines 16 and 18 already say it).

> "**Ticket is MINIMAL. Plan contains ALL details.**" *(45)*

Stated in the Output table it sits under, again as the Step 3 heading, again in the Rules bullet, and again in `dor.md`. Four copies of five words.

---

## Grade

**2/5.** The skill's *content* is good — the DoR is coherent, the phase contract is precise enough to gate on, the ticketing reference does the hard thinking about contradicting comments, and the Execution Surface heuristic is genuinely useful. What sinks it is that the one section written as a rigid, no-deviation procedure — "Execute these 6 commands IN ORDER. No explanations." — contains an unexecutable command (`{codename}` defined nowhere in the plugin), a shell block that misreports its own most likely failure while pushing to `main` ungated, and a duplicate of Step 3. Around it, Step 4's blast-radius block hard-errors in any repo that does not vendor `scripts/graphify/`, while telling me it would fail silently. Two of the five loaded spec files disagree with the SKILL on the plan's required frontmatter and on how much belongs in a ticket, and in both cases the SKILL is the one that points *at* the file that contradicts it. And this scenario's own premise exposes the sharpest gap: I resolved two contradictions and parked an open question, and the skill gives me no step to say so on the ticket or to move it off Backlog — so `/we:orchestrate` Step 3 signals 1 and 5 will fire on the untouched comments and send my approved plan straight back to the refine lane, which is the exact loop this skill exists to close. Set against that, roughly 90 of 396 lines are restatements — the epic-vs-phases rule four times, "ticket is minimal" four times, the stop-after-step-6 boundary three times — so the file is simultaneously too long and missing its load-bearing mechanics.
