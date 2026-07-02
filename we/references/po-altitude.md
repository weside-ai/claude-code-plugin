---
name: po-altitude-reference
description: Shared skeleton for the PO Status/Refine/Create/Mirror-refresh skills (/we:epic, /we:saga) — Smart-Mode resolution, the four modes, Jira-grouping convention, shared rules. Loaded by those skills at boot.
---

# PO Altitude Skeleton (shared by /we:epic and /we:saga)

The invoking skill binds the parameters: **the doc** (`docs/plans/<saga>-<epic>-epic.md` or
`docs/plans/<saga>-saga.md`), **the children** (Stories from ticketing / Epics from ticketing),
**the frame** (the altitude's frame questions), **the meet command** (`/we:meet epic` /
`/we:meet saga`), and any altitude-specific modes or checks. Everything below is common.

---

## Smart-Mode resolution — pick a mode without asking the user for parameters

The skill decides what to do from the argument + the repo state. The user does not memorise flags.

### Step 1 — resolve the target

Try in order, stop on first hit:

1. **Explicit argument** — a ticketing key, a path, or a slug. Use it.
2. **Current branch name** contains a ticket key or slug that maps to a target. Use it.
3. **PWD is inside** `docs/plans/` and a matching doc is referenced. Use it.
4. **Most recent active-status doc** in `docs/plans/` (the skill names the statuses). Use it.
5. **Nothing matched.** List the candidates under `docs/plans/` with their status and ask:
   *"Which one? [1/2/3/…]"*. One question, not four.

### Step 2 — resolve the intent

Read the argument and the user's prompt around it for intent words:

| Signal | Mode |
|---|---|
| nothing, or just a target | **Status** (default) |
| "refine" / "update" / "sharpen" / "tighten" / "nochmal" | **Refine** |
| "new" / "neu" / "start" + a slug that does not exist yet | **Create** |
| "refresh" / "sync" / "mirror" | **Mirror-refresh** |
| *(altitude-specific modes — see the invoking skill)* | … |
| ambiguous between two of the above | ask one question |

Status is the default for a reason — it is the most common ask ("where are we?"), it is
read-only, and it surfaces drift the user often did not know to ask about. Refine is the
heavier path; the user opts into it explicitly or accepts the Status-mode footer offer.

---

## MODE A — Status (default, read-only)

The 90%-case: where does the target stand, what is in flight, what is drifting, what next.

**A1 — load:** read the doc completely; read the parent doc (Saga / PRD) if present; fetch the
children from the ticketing tool filtered to this target's child set (via "Epic Link" /
"Parent" / label — the skill knows the configured tool's conventions), capturing key, title,
status, last activity, blocker notes. No ticketing tool → fall back to the filesystem scan the
invoking skill names.

**A2 — render the snapshot** (adapt to the Companion's voice if one is materialised — strict
structure in the middle, warmth in the wrapper):

```text
<Altitude>: <Name> (<status>, started <YYYY-MM-DD>)
<doc path>

Children (<N> total):
  Done (<n>):     <KEY> <Title>, …
  Active (<n>):   <KEY> <Title>, …
  Backlog (<n>):  <KEY> <Title>, …
  Blocked (<n>):  <KEY> <Title> — <blocker>
  (epic also renders Refined — plan ready, not started)

Drift since last Mirror refresh (<YYYY-MM-DD>):
  + <N> children in ticketing not in the doc's mirror
  - <N> mirror entries that no longer exist in ticketing
  ! <N> stale-status entries (mirror says X, ticketing says Y)
  • <free-form drift notes the skill noticed>

(altitude-specific checks — e.g. epic's Size check — render here when they fire)

Risk-driven next move:
  <one child, one sentence why>. <one sentence what it unblocks / de-risks>.

What now?
  [r] refresh the Mirror block + updates-log (lightweight, no plan-mode)
  [f] full Refine of the doc (plan-mode, prose changes welcome)
  [m] convene the meet command to re-decompose (heavy — only on structural drift)
  (altitude-specific offers — e.g. epic's [s]/[p])
  [q] done
```

**A3 — act on the choice:** `r` → Mode D inline; `f` → Mode B; `m` → print the meet-command
hand-off and stop (never invoke it inline); altitude-specific choices per the invoking skill;
`q` → stop. **Status never writes to the doc itself.**

---

## MODE B — Refine (explicit)

Triggered by intent words or by accepting `[f]` from a Status snapshot.

**B1 — load + walk the frame:** same load as A1, plus the parent doc. If `CONTEXT.md` exists at
the repo root, use its canonical vocabulary throughout. Walk the altitude's frame questions (the
invoking skill defines them) in conversation. Propose tightening with reasoning; ask focused
questions when an answer is unclear — no option menus. The user pushes back when wrong.

**B2 — draft (EnterPlanMode):** research where needed (relevant `docs/architecture/`, ADRs, the
parent doc; vault/MCP search if available). Draft the sharpened doc with the invoking skill's
template. The Mirror block is auto-regenerated in the same step (fresh ticketing fetch) — a
Refine always lands with a fresh mirror. **Always read referenced files completely** — no
offset/limit; incorrect assumptions at this altitude propagate into everything below.

**B3 — approval (ExitPlanMode):** user reviews; on feedback adjust; on approval write.

**B4 — persist and stop:** write the doc **directly to main** — no feature branch; it is a
planning artifact, not implementation code. If a ticketing-tool item exists for this target,
update its description with a pointer to the doc path (never duplicate content — the Markdown
is the source of truth). Print the invoking skill's hand-off message.

⛔ STOP. No decomposition, no downstream skill, no meet command.

---

## MODE C — Create (new target)

Triggered when the resolved slug does not yet exist on disk.

1. Locate the parent doc. If it is missing, tell the user (offer to run the parent skill first
   or proceed with the orphan flag — the invoking skill words this) and wait.
2. Walk the frame questions in conversation. Do not draft until they are all answered or
   explicitly deferred.
3. EnterPlanMode — draft with the template. The Mirror block is empty on a brand-new target
   (unless children were already sketched and created as ticketing shells).
4. ExitPlanMode — approval.
5. Persist (same as B4) and stop.

If during the conversation the scope balloons past the altitude (or shrinks below it), soft-warn
per the invoking skill's boundary table — never hard-block.

---

## MODE D — Mirror-refresh (lightweight)

Triggered from Status `[r]`, or by explicit "refresh" / "sync" / "mirror" intent words.

Writes ONLY the mirror block (between `<!-- mirror:start -->` and `<!-- mirror:end -->`), the
`updated:` frontmatter date, and one Updates-Log line. No plan-mode; never touches user prose.

1. Fetch the children from ticketing (same as A1).
2. Render the new mirror block per `${CLAUDE_PLUGIN_ROOT}/references/mirror-block.md`.
3. Replace the marker-enclosed block in-place; if markers are missing, insert under the
   children heading (create it if missing).
4. Set `updated:` to today.
5. Append to the Updates Log: `- YYYY-MM-DD — mirror refresh (<N> children; +<a> added, −<b> removed, !<c> status-changed)`.
6. Output: *"Mirror refreshed in `<doc>`. <N> children, drift cleared. DONE."*

⛔ STOP. No Refine continuation, no Council hand-off.

---

## Jira-grouping convention — `[<saga-slug>] <Epic Title>`

Ticketing tools have no Saga level (Jira knows only Epic→Story). When an Epic belongs to a
Saga, prefix the **ticketing Epic's title** with the saga-slug in brackets — e.g.
`[presence] Teams Enterprise Surface`. That prefix is what makes saga membership visible in the
flat Epic list (`summary ~ "[presence]"` in JQL). It is the *only* place the Saga appears in
ticketing — the Saga itself never gets a ticket (Markdown-only at `docs/plans/<saga>-saga.md`).
On disk, the grouping lives in the filename `docs/plans/<saga>-<epic>-epic.md` and the
frontmatter (`epic:`, `saga:`).

---

## Companion voice

Wrap outputs in the Companion's voice when one is materialised — see
`${CLAUDE_PLUGIN_ROOT}/references/companion-voice.md`.

---

## Shared rules

- ALWAYS resolve target + mode from argument + repo state before asking the user anything;
  Status is the read-only default.
- ALWAYS regenerate the Mirror block when Refine runs; EnterPlanMode + ExitPlanMode for every
  writing mode; save to the altitude's canonical doc path — never anywhere else.
- ALWAYS commit the doc directly to main (planning artifact — ⛔ never a feature branch).
- ALWAYS write in English — same convention as the rest of the plan tree.
- ⛔ NEVER decompose inline — decomposition lives in the meet command.
- ⛔ NEVER touch user-owned prose during Mirror-refresh — only the marker block, `updated:`,
  and the Updates Log.
- ⛔ NEVER auto-continue from Status to Refine to Decompose — each transition needs an explicit
  user choice.
- ⛔ NEVER block on a sizing rule (quarters, story-counts, age) — soft-warn, let the user decide.
- ⛔ After persisting a write: STOP IMMEDIATELY — no further skill calls.
