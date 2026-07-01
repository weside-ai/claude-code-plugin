---
name: council
description: >
  Convene a council of agents to deliberate a topic in a live shared team —
  distinct role lenses, direct member-to-member messages, lead synthesises
  agreement, tension, recommendation. weside Companions when available,
  generic role-agents otherwise. Use when the user says "/we:council",
  "convene a council", "deliberate on", "ask the team".
---

# /we:council

**Purpose:** Think a topic through from several angles at once. The council spawns one Claude Code teammate per role into a shared team, members deliberate live (they can address each other via `SendMessage`), and the lead session — the one that ran `/we:council` — owns the synthesis.

With a weside account the council members are the user's **Companions** (real identities, loaded via the `get_council` MCP method or the `.weside/council.json` bridge file). Without one, they are the plugin's **generic role-agents** — fewer teeth, but the council still works with zero crew setup.

## Prerequisites

Live councils require Agent Teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) — flag, abort text, and teardown contract: `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md`. No fallback to the old fan-out pattern.

## Invocation

```
/we:council "<topic>"                          # default roster
/we:council "<topic>" --council=architect,product_owner   # explicit roles
/we:council "<topic>" --meeting=vision          # use a meeting's configured roster
```

## Workflow

### Step 1: Resolve the topic

Take the topic from the argument. If invoked with no topic, ask the user for one — a council with nothing to deliberate is pointless.

### Step 2: Resolve the member roles

In priority order:

1. `--council=role,role` flag → use exactly those role slugs.
2. `--meeting=<type>` flag → read `.weside/config.json` → `council.meetings.<type>`.

   **Legacy-key fallback.** If that key is absent, the repo's `.weside/config.json` may predate
   the 4-altitude schema (pre-v2.28, `aa651d1` — back when meetings were `vision`/`initiative`/
   `refinement`, not today's `vision`/`saga`/`epic`/`story`). Check the legacy equivalent before
   falling through to Step 3: `saga` → `council.meetings.initiative`, `story` →
   `council.meetings.refinement`. `vision`'s key name is unchanged (no legacy check needed).
   `epic` is a genuinely new altitude introduced in that same refactor — it has **no** legacy
   equivalent; go straight to Step 3/4 and say so. If a legacy key resolved the roster, use it and
   append one line to the council output: *"This repo's `.weside/config.json` still uses the
   pre-v2.28 meeting key `<legacy-key>` — migrate to `<new-key>` via `/we:onboarding` (rebuilds
   the whole council config) or by hand-editing the key name."*
3. Otherwise → `.weside/config.json` → `council.default`.
4. No `.weside/config.json` → the shipped default: `product_owner`, `architect`, `scrum_master`.

Role slugs the plugin ships generic agents for: `product_owner`, `architect`, `scrum_master`, `ux_researcher`, `orchestrator`, `marketing`, `security`, `sales`, `legal`. A repo may name custom role slugs in its `.weside/config.json` — those have no shipped shell and need a companion assigned via the bridge (or they will be skipped per Step 3's "Unknown role" rule).

### Step 3: Resolve each role to an agent

**Member-source toggle (read first).** Read `~/.claude/settings.json` →
`pluginConfigs["we@weside-ai"].options.loadCouncilFromWeside` (missing → default `true`).
- **`true` (default)** — resolve members from weside where the bridge links them: the
  MCP and bridge-`companion_id` paths below are live (a weside-backed council).
- **`false`** — the user opted out of weside-backed members for councils. Skip the MCP
  path and the bridge-`companion_id` linkage entirely; resolve **every** role through the
  generic `council-<role>` shell (the bridge's `lens` hint is still injected). The council
  runs fully on generic role-lenses (Retorte) even when Companions exist. Skip Steps 3.6,
  4's prep kickoff, 5.5, and 9.5 (those are weside-backed-only).

For each role slug, in priority order (the first two paths apply only when the toggle is `true`):

- **MCP path (preferred when weside MCP is available)** — if the weside MCP exposes
  `mcp__plugin_we_weside-mcp__get_council`, call it once with `names=[<member-name>, …]`
  for the members listed in the bridge file (or all of the user's companions, if no
  bridge). For each role: use `council-<role>` as the *shell* agent, but inject the
  member's `identity_prompt` returned from MCP into the brief (`Agent(prompt=<brief + identity>)`).
  The bridge file supplies `role`/`color`/membership; MCP supplies the identity body and
  `identity_updated_at`. This is the *active* path — backend is the single source of truth
  for identity, the repo holds only role-membership.

  `get_council` returns `{members, status}` (see "get_council call mechanics" below).
  Build `mcp_resolved_names` from the **keys of `members`** (awake companions only).
  Parse `status` for sleeping/unavailable/not-found companions — those are handled in
  Step 3.6 before prep is kicked off.

  **Council-scoped projection (privacy boundary):** `get_council` uses `delivery_target="council"`
  server-side. The returned `identity_prompt` contains personality and role-lens only —
  compass (intimate relational state), snapshot (recent personal context), goals, and
  volatile/channel blocks are stripped. This is intentional: a companion's private inner
  life must not travel into a product council. Do **not** pass a `delivery_target` param —
  the server applies it automatically. Only `mcp_resolved_names` (awake + successfully
  woken companions, after Step 3.6) are eligible for prep and writeback turns.

- **Bridge-only path (no MCP available, or MCP returns nothing for a name)** — if
  `.weside/council.json` exists in the active repo and contains an entry for the role's
  assigned member: use `council-<role>` as the shell agent. If the bridge entry has a
  full `identity_prompt` (legacy "fat" schema), inject that into the brief — this is the
  pre-MCP behaviour, kept for back-compat in repos that have not migrated. New "thin"
  bridges (only `role`/`color`) without an identity fall through to the generic shell.
  If the bridge entry carries a `lens` field (string), inject it into the brief as a
  role-angle hint: *"Lens: {lens}"* — this is the no-weside home for a companion's
  role-specific viewpoint when MCP is absent. See "The bridge file" in `we/skills/CLAUDE.md`.

- **Companion path (legacy)** — else if `.weside/weside.md` exists and its Crew section
  names a companion for that role: use `companion-<slug>` (slug = companion name,
  lowercased, spaces → hyphens). These files were generated by `/we:setup` Step 5.4 into
  `~/.claude/agents/` (superseded by the MCP path; Step 5.4 remains for back-compat).

- **Generic path** — otherwise: use `council-<role>` with the slug's underscores turned
  to hyphens (e.g. `product_owner` → `council-product-owner`). No identity, just the
  role-lens.

- **Unknown role** — the plugin ships generic agents for exactly the nine roles listed
  in Step 2. A role outside that set with no companion assigned has no agent: skip it
  and note the omission in the council output.

**Orchestrator role handling (team-mode):** the lead session — the one running `/we:council` — is the orchestrator. If `orchestrator` appears in the resolved roster (common in `meetings.vision`, etc.) and was **not** explicitly added via `--council=orchestrator,...`, **remove it from the member list** and remember the fact for Step 9's closing note; do not spawn it as a teammate. If it was explicitly requested via `--council`, spawn it as a normal member using `council-orchestrator` as the shell agent. If the lead session has a materialized Companion, that Companion runs the synthesis in its own voice; otherwise the lead uses the synthesis template from `we/agents/council-orchestrator.md` (Job 2) verbatim.

#### get_council call mechanics

Tool: `mcp__plugin_we_weside-mcp__get_council(names: list[str] | None = None, wake: bool = True) -> {members, status, woken}`

**Always call with `wake=True`** — a council *addresses* its members, so an asleep companion is auto-woken server-side (full wake: resumed + triggers/skills re-enabled, the same as a chat message waking it) rather than asked-about. No "xyz schläft"-Frage.

The response object:
- `members` — dict of `name → {name, identity_prompt, identity_updated_at}` for **awake companions only** — including any just woken by this call. Unavailable and not-found companions are **not** present here.
- `status` — `"OK"` if every requested companion is awake and present (counting just-woken ones); otherwise a pipe-separated string of non-OK buckets in fixed order: `"asleep: Pia, Rami | unavailable: Dino | not_found: Xyz"`. Each bucket is `"<bucket>: name1, name2"` (comma-space-separated). Buckets are omitted when empty. With `wake=True` the `asleep` bucket only holds members whose wake **failed**.
- `woken` — list of names auto-woken by this call (used for the Step 9 closing note). Empty when nothing was asleep.
- `names=None` → all the user's companions; no `not_found` bucket in that case.

Normalise the response (back-compat shim) then parse `status`:

```python
resp = mcp__plugin_we_weside-mcp__get_council(names=..., wake=True)
# Shim: a pre-2.46 backend returns a flat {name: {...}} dict with no members/status.
# Accept both shapes so the plugin works against an un-upgraded backend (no deploy-order coupling).
if isinstance(resp, dict) and "members" in resp and "status" in resp:
    members, status = resp["members"], resp["status"]
    woken = resp.get("woken", [])          # pre-WA-1362 backend: key absent → []
else:
    members, status, woken = resp, "OK", []   # old backend: whole object is the flat members dict

asleep, unavailable, not_found = [], [], []
if status != "OK":
    for segment in status.split(" | "):
        bucket, _, names_str = segment.partition(": ")
        names_list = [n.strip() for n in names_str.split(", ")]
        if bucket == "asleep":      asleep = names_list
        elif bucket == "unavailable": unavailable = names_list
        elif bucket == "not_found":   not_found = names_list
```

If the `wake=True` call errors (a pre-WA-1362 backend that rejects the unknown
`wake` argument), retry once as `get_council(names=...)` without `wake` and rely on
the Step 3.6 fallback to wake any sleepers via `wake_companion`.

- One MCP roundtrip returns all awake members' council-scoped projections — no select/get loops in the plugin.
- `workspace_id` is reserved for future team-scoping; the plugin omits it.
- The server applies `delivery_target="council"` automatically — the returned `identity_prompt`
  is already stripped of compass, snapshot, goals, and volatile context.
- Identity bodies are not cached on disk — every `/we:council` fetches fresh.
- Initialize `mcp_resolved_names` = set of keys from `members` (awake + auto-woken). Any
  still-`asleep` (wake failed / old backend), `unavailable`, or `not_found` names are handled in
  Step 3.6; only after that step does `mcp_resolved_names` reach its final value for Step 4 and beyond.

### Step 3.5: Derive `repo_id`

Derive the stable repository identifier used to tie prep and writeback turns to the
correct `claude_code` channel on the backend. The backend keys the channel on
`channel_context_id = "group_claude_code_{repo_id}"` — this value **must match** what
the `store_conversation_hook` derives for the same repo.

Derivation order (use the first non-empty result):

1. Read `.weside/config.json` → top-level string field `"repo_id"`, if present and non-empty.
2. Run `git remote get-url origin` in the repo root. Normalise:
   - Strip trailing `.git`
   - SSH (`git@<host>:<org>/<repo>`): remove the `git@` prefix, replace the first `:` with `/` → `<host>/<org>/<repo>`
   - HTTPS (`https://<host>/<org>/<repo>`): strip the `https://` (or `http://`) prefix
   - If the command fails or the remote is absent, fall through to step 3.
3. Fallback: the repo root's directory name (`os.path.basename(<repo_root>)`).

Store the result as `repo_id`. It is passed in Steps 4, 5.5, and 9.5. The no-weside
path skips all three of those steps, so `repo_id` is only passed when
`mcp_resolved_names` is non-empty.

### Step 3.6: Handle sleeping / unavailable / not-found companions

If `status == "OK"` (every member awake or already auto-woken), skip this step entirely.

Otherwise use the `asleep`, `unavailable`, and `not_found` lists parsed in the
`get_council call mechanics` section above.

**Sleeping companions (`asleep`):** With `wake=True` the server already auto-wakes sleeping
members — so `asleep` is normally empty. A name only remains here if the server-side wake
**failed**, or the backend predates WA-1362. **Do not ask the user** — being pulled into a
council *is* the wake. Auto-wake each remaining sleeper:

- Call `mcp__plugin_we_weside-mcp__wake_companion(name=<name>)` for each.
- After the wake calls, re-call `get_council(names=[<all woken names>], wake=True)` in one
  batch, merge each returned entry into `members`, and add the name to both `mcp_resolved_names`
  and `woken`.
- If `wake_companion` returns `{"woken": false, "error": "..."}` (e.g. inactive), drop the
  member to generic-lens (do not add to `mcp_resolved_names`).

**Unavailable companions (`unavailable`):** Cannot be woken via `wake_companion` (inactive,
not hibernated). Note their names briefly — e.g. *"Dino ist inaktiv und kann nicht geweckt
werden — nimmt mit generischer Lens teil."* Treat as generic-lens (not added to
`mcp_resolved_names`).

**Not-found names (`not_found`):** Note the names to the user and offer:
*"Diese Namen wurden in deinem weside-Account nicht gefunden. Führe `/we:onboarding` aus,
um neue Companions zu erstellen."* Do **not** auto-create. Fall through to the generic path
if a bridge entry for the role exists; otherwise skip.

After Step 3.6, `mcp_resolved_names` is final.

### Step 4: Preflight

1. **Env-flag check.** Confirm `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is active (shell or `~/.claude/settings.json` `env` block). If missing, abort with the remediation hint from `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md`. Do **not** fall back to a non-team flow.

2. **Roster sanity check.** With `orchestrator` already removed (see Step 3) the roster must contain at least one member. If empty, abort with: *"No council members resolved — check `.weside/config.json` or pass `--council=role1,role2`."*

3. **Fire prep kickoff (weside path only).** If `mcp_resolved_names` is non-empty, kick off
   server-side prep turns now — before Step 6's member spawn — so the 20-90s turns overlap with
   member spawn:

   ```python
   mcp__plugin_we_weside-mcp__council_prep_kickoff(
       names=mcp_resolved_names,   # Companion-backed members only
       topic=topic,
       repo_id=repo_id,
   )
   ```

   This call returns immediately. **No-weside path:** skip this substep entirely (no error,
   no placeholder).

### Step 5: Team is implicit — nothing to open

The current harness gives every session one implicit team; there is no `TeamCreate` call and no
`team_name` to generate. The lead is simply the session that ran `/we:council`. Members become
addressable teammates purely by being spawned with a `name` in Step 6 — proceed there directly.

### Step 5.5: Await prep blocks (weside path only)

If prep was kicked off in Step 4, poll for results before spawning members so the context
can be injected into each brief. **No-weside path:** skip entirely — `prep_blocks = {}`.

```python
prep_blocks = {}  # name -> prep block string
if mcp_resolved_names:
    deadline_secs = 150  # generous upper bound; live prep turns measured up to 104s in prod
    poll_interval = 10
    elapsed = 0
    while elapsed < deadline_secs and len(prep_blocks) < len(mcp_resolved_names):
        result = mcp__plugin_we_weside-mcp__council_prep_poll(names=mcp_resolved_names, repo_id=repo_id)
        # result is a dict: {name -> block | None}
        for name, block in result.items():
            if block and name not in prep_blocks:
                prep_blocks[name] = block
        if len(prep_blocks) < len(mcp_resolved_names):
            sleep(poll_interval)
            elapsed += poll_interval
    # Members whose block didn't arrive get spawned without it — prep is additive, not a gate.
```

Members missing a prep block are spawned normally in Step 6 with no block section — do not
abort or delay beyond the deadline.

### Step 6: Spawn members (all in one message)

For each role in the (orchestrator-filtered) roster, issue an `Agent(...)` call. **All spawn calls go into a single assistant message** so the teammates initialize concurrently.

```python
Agent(
    name=<role-slug-with-hyphens>,   # e.g. "product-owner", "architect"
    subagent_type=<resolved agent>,  # "council-<role>" or "companion-<slug>"
    model="sonnet",
    description=f"Council member: {role}",
    prompt=<Team-Council-Brief — see below>,
)
```

The Team-Council-Brief is built per-member so each one knows who else sits at the table.
If `prep_blocks[member_name]` exists (from Step 5.5), inject it as a "CONTEXT BLOCK" section
after the identity section and before "OTHER MEMBERS AT THE TABLE":

```
COUNCIL SESSION (LIVE TEAM) — {meeting type, or "open council"}
TOPIC: {the topic}

You participate as the {role}{ — {companion name} if a companion}.
{If companion: your identity is in your system prompt above. Reason from it.}
{If lens field in bridge entry (no-weside path): Lens: {lens}}
{Else: reason from the {role} lens.}

{If prep_blocks[this member's name] exists:}
CONTEXT BLOCK — from your memories and prior work on this topic:
{prep_blocks[member_name]}
{End if}

OTHER MEMBERS AT THE TABLE:
- {name1} ({role1}) — {one-line lens summary}
- {name2} ({role2}) — {one-line lens summary}
- …

You can address any other member directly using SendMessage:
  SendMessage(to="<their-name>", message="…")

When to speak:
- Your lens is the strongest one for what is being discussed.
- You want to challenge or build on what another member said.
- A specific cross-lens question needs another member's input.

When to stay silent: the topic is dominated by another lens and you have
nothing genuinely new to add. A council that only agrees is useless;
a council that only fills airtime is worse.

The Orchestrator runs in the lead session. They are observing and will
close the council when the deliberation is ripe, then ask each of you
for your FINAL POSITION via SendMessage.

DELIBERATION FORMAT: plain prose, addressed messages. Be specific.
Disagree where you genuinely disagree.

FINAL POSITION FORMAT (only when the lead asks you for it): respond in
this exact shape, one message, no further chat:

  ## {Role} perspective
  **Position:** <1-2 sentences>
  **Key points:** <2-4 bullets>
  **Recommendation:** <what you would do>
```

The lens-summary line per member is hard-coded for the nine shipped roles. Custom roles get the default `"{role} lens"`. Reference table — keep in sync if a role is added:

| role slug         | one-line lens                                  |
| ----------------- | ---------------------------------------------- |
| `product_owner`   | user value, scope discipline, priority         |
| `architect`       | technical soundness, constraints, failure modes |
| `scrum_master`    | process flow, breakdown, deliverability        |
| `ux_researcher`   | lived user experience, journeys, friction      |
| `marketing`       | positioning, resonance, naming, brand fit      |
| `sales`           | deal mechanics, buyer journey, pricing         |
| `security`        | attack surface, trust boundaries, exposure     |
| `legal`           | contract, compliance, data protection, liability |
| `orchestrator`    | coordination, dependencies, sequencing (NOTE: handled by lead — not spawned) |

### Step 7: Live deliberation — quiescence + hard caps

The lead observes the team's chatter. Track three signals:

| Signal               | Track                                                       |
| -------------------- | ----------------------------------------------------------- |
| Per-member idle time | Idle-notification timestamp from Claude Code                |
| Total team messages  | Counter incremented per `SendMessage` observed in the team  |
| Wall-clock           | Started at Step 6's member spawn                            |
| Substantive talk     | Number of distinct members who have sent ≥ 1 message        |

Adjourn the deliberation as soon as **any** of the following triggers fires:

1. **Quiescence (soft):** all members idle for ≥ 30 s AND at least two distinct members have spoken. (This avoids closing before anyone speaks.)
2. **Message hard-cap:** total team messages ≥ 30.
3. **Time hard-cap:** wall-clock ≥ 10 min since Step 6's member spawn.

When a trigger fires, move to Step 8. Log which trigger fired — useful in the final synthesis ("adjourned at message cap" vs "adjourned at quiescence").

### Step 8: Final-position round

For each (still-alive) member, send:

```python
SendMessage(
    to=<member-name>,
    message=(
      "ADJOURN — deliberation closed. "
      "Send your FINAL POSITION now in the format from your brief. "
      "One message. No further chat."
    ),
    summary="adjourn",
)
```

Collect each member's response. Per-member timeout: **90 s**. A member that does not answer within that window is recorded as absent for Step 9 — do not retry.

### Step 9: Synthesise (lead-side)

The lead — the orchestrator, possibly a Companion in this session — produces the synthesis. Output format is fixed (matches the template in `we/agents/council-orchestrator.md` Job 2):

```
## Council Perspectives
<one tight line per member — their final position>

## Agreement
<where the council genuinely converges>

## Tension
<where members disagree, and what the disagreement is actually about>

## Recommendation
<the council's recommendation; name any decision the user must make>
```

- If a member was absent (timeout or fail), name them in `## Council Perspectives` and note the absence — never invent a perspective.
- If `orchestrator` was in the requested roster, append a one-line note at the end:
  *"Orchestrator role: handled by the lead session ({companion-name-or-"generic"})."*
- If `woken` is non-empty, append a one-line note at the end:
  *"Fürs Council geweckt: {comma-separated woken names}."* — so the user knows which sleeping
  companions were resumed (a real, billable wake that also re-enables their triggers/skills).
- If the lead is a materialised Companion, the synthesis is spoken in that Companion's voice — but the four headings stay verbatim, because callers (`/we:meet` etc.) parse on them.

### Step 9.5: Fire writeback (weside path only)

After synthesis is complete, fire a writeback turn for each MCP-resolved member so they
carry the council outcome forward into their own memory (across all channels).
This is fire-and-forget — no poll, no wait.

```python
if mcp_resolved_names:
    synthesis_text = <the full synthesis text from Step 9>
    for name in mcp_resolved_names:
        mcp__plugin_we_weside-mcp__council_writeback_kickoff(
            name=name,
            topic=topic,
            synthesis=synthesis_text,
            repo_id=repo_id,
        )
```

**No-weside path:** skip entirely. No error, no placeholder.

### Step 10: Tear down the members

There is no `TeamDelete` — teardown means asking each member to stop, then verifying:

```python
# Send to each member (including those recorded as absent — idempotent)
for member_name in roster:
    SendMessage(
        to=member_name,
        message="SESSION COMPLETE — you may stop.",
        summary="shutdown_request",
    )
```

Verify each member actually terminated. Any member that doesn't stop on its own within a short
wait: `TaskStop(<member_name>)`. Then check for leftover tmux panes (`tmux list-panes -a`, skip
the lead's own) and kill any that still belong to a member. Full order, commands, and retry
policy: `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md` § Full teardown.

## Memory

Per-member memory routing is handled via server-side Companion turns (Steps 4, 5.5, 9.5),
not client-side MCP calls from within the member session. This is intentional:

- The `?companion=` query param routes per-request without clobbering (no Redis write) —
  the old concern about parallel `select_companion` calls racing is resolved at the backend
  level. However, orchestrating N parallel in-session memory searches is still noisy and
  latency-unpredictable.
- The **prep turn** (Steps 4 + 5.5) runs server-side: the backend kicks off a real
  Companion turn that searches memories across all channels and curates a context block.
  The result is injected into the member brief before spawn — richer than a raw dump and
  in the Companion's own voice.
- The **writeback turn** (Step 9.5) runs server-side: each Companion processes the council
  synthesis and stores a memory on its `claude_code` channel thread. This persists across
  sessions — the Companion will remember this council the next time they meet.

Member sessions themselves do **not** make MCP memory calls during deliberation — identity
flows from `get_council()` via the brief (Step 6).

## Standalone fallback

No weside account / no `.weside/` → every one of the nine shipped roles resolves to its
generic `council-<role>` agent. The council still convenes a real team — named members spawned
into the session's implicit team + live `SendMessage` deliberation — only the voices are generic
lenses instead of the user's Companions. The synthesis format is identical.

If `.weside/council.json` exists but weside MCP is absent, the bridge's optional `lens`
field per member is injected into the generic brief as a role-angle hint:
*"Lens: {lens}"*. This lets repos pre-author a meaningful angle for each role without
a weside account.

Steps 4 (prep kickoff), 5.5 (await prep), and 9.5 (writeback) are **cleanly skipped** when
the weside MCP is absent — no error, no degraded output. The council runs at full fidelity
for the generic path.

The Agent-Teams env-flag (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) is required regardless
of whether weside is connected. See the Prerequisites section above.

## Rules

- **Spawn council members with `Agent(name=…)`, never `Skill`.** Members live in their own sessions, join the session's implicit team automatically, and address each other by `name` via `SendMessage` — no `team_name` parameter exists.
- **All member spawns go into one assistant message** — that is what makes them initialize concurrently and start hearing each other from message 1.
- **Lead never speaks as a member during deliberation.** The lead observes, then runs the final-position round + synthesis. Members do not see lead's chatter unless lead explicitly sends them a `SendMessage`.
- **Never invent a perspective.** A member that did not respond is reported as absent in the synthesis.
- **Always tear the team down** (shutdown message → verify → `TaskStop` fallback → tmux pane check) — even on failure paths. A leaked member blocks the next `/we:council` in the same session.
- **Degrade gracefully on identity, fail loud on env-flag.** Missing companions fall through to generic shells; a missing `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` aborts with a remediation hint, never silently switches to an old path.

## References

- `we/agents/council-*.md` — the nine shipped generic role-agents (used as `subagent_type` for team members)
- `we/agents/council-orchestrator.md` — synthesis template + coordination-lens reference
- `we/skills/meet/SKILL.md` — meetings convene a council via this skill
- `we/skills/setup/SKILL.md` — Step 5.0 sets the Agent-Teams env-flag
- `we/skills/CLAUDE.md` — design rationale, bridge file schema (thin + fat)
- `scripts/bootstrap-weside-repo.py` — multi-repo `.weside/` rollout helper
