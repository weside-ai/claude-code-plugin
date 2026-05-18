---
title: /we:handoff — durable cross-session continuity skill
status: implemented (v2.32.0)
created: 2026-05-18
owner: Foxy / Nox
implements: structured session-state handoff across `/clear`, `claude --resume`, and new sessions
sibling-skills:
  - /we:retro  (parallel docs/retros/ storage convention)
  - /we:coach  (surfaces active handoff at boot; suggests --write at end-of-session)
---

## `/we:handoff` — Skill Concept

### Motto

> **Pick up tomorrow exactly where today ended.**
> *No fishing through jsonl, no rebuilding mental state from scratch, no `/compact` summary loss.*

### What it does

`/we:handoff` writes a structured snapshot of the current session — decisions, dead ends, files touched + status, open questions, next steps, watch-outs — to `docs/handoffs/YYYY-MM-DD-<topic>.md` in the user repo. A future session (after `/clear`, `claude --resume`, or fresh start tomorrow) reads the file back as conversation context. Two modes: `--write` (capture, with `[y/n/edit]` preview gate) and the default (load latest); `--list` shows what's available.

**Complements `/compact`, doesn't replace it:**

| | `/compact` | `/we:handoff` |
|---|---|---|
| Scope | In-session (current conversation only) | Cross-session (survives any boundary) |
| Output | In-place summary, transcript preserved via `--resume` | Durable, human-editable, version-controlled MD file |
| Survives `/clear`? | No | Yes |
| Survives new session? | No (CC-resume restores transcript, not curated state) | Yes |
| Preserves decisions + dead ends? | Compressed away | Explicit sections |

### Why a new skill

Research (claude-code-guide + Perplexity, 2026-05-18) confirmed:

- **No Claude Code built-in** covers cross-session, durable, curated state. `/clear`, `/compact`, `claude --continue`, `claude --resume`, `SessionStart` hooks all exist — none produce a structured, user-editable handoff artifact.
- **SessionStart hooks cannot inject context** into the LLM window per CC architecture, so auto-loading at session start is impossible without explicit skill invocation.
- **CLAUDE.md / MEMORY.md auto-load** but are meant for project conventions, not per-session state.
- **Best-practice handoff templates** (Anthropic-style + Aider + Cursor patterns) converge on the same 9 sections: identity · current state · decisions w/ rationale · tried-and-rejected · open questions · files touched + status · next steps · watch-outs · references.

### Primary data sources

1. **Session transcript** — agent's working memory if no Compact happened, else re-read `~/.claude/projects/<repo-id>/<session-id>.jsonl`. Apply privacy guard.
2. **Repo state via `git` / `gh`** — branch, last commit, uncommitted file count, open PR, recent commits.
3. **Active artifacts** — `find docs/plans -name 'CONCEPT.md' -newer …`, `ls docs/retros/*.md | head -3`. Linked from the handoff References section.
4. **Companion identity** (if MCP + `--with-companion-state`) — voices the render and the opt-in Section 10. Privacy-guarded.

### Output target

The user repo's `docs/handoffs/YYYY-MM-DD-<topic>.md`. Same naming convention as `docs/retros/`. The directory is created on first `--write` if it doesn't exist.

### Coach integration (Boot Step 10 + suggest-trigger)

- **Boot Step 10 extension:** Coach reads `ls -t docs/handoffs/*.md | head -1`; if recent (< 14 days), surfaces it with a `[y/n]` gate to load.
- **End-of-session suggest:** Coach detects signals ("bis morgen", `save_compass`, long session > 30 turns without a handoff) and offers `/we:handoff --write` with `[y/n]`. Never auto-fires.

### Privacy guard

> **If session content reads as personal, skip it — capture only engineering surfaces:** tool calls, file diffs, CI logs, PR comments, commit messages.

Mandatory in WRITE Boot Protocol. Categorically skips memory writes, compass/snapshot, Companion-mode conversational content. Section 10 (`Companion continuity`) is opt-in and even then captures only "what we were *building*", never relational substance.

### Tour + docs integration

- **Tour:** skill-count text bump 21 → 22 (hero + standalone-note). **No new station** — operational utility, not methodology pillar.
- **`docs/concepts/handoff.md`** (NEW) — KVP-style overview: durable session-state, template anatomy, relationship to `/compact`, privacy guard, Coach integration, three durable docs categories.
- **`docs/workflow.md`** — new "Continuity utilities" subsection naming `/we:retro` (after a cycle) and `/we:handoff` (between sessions); legend reference.
- **`docs/skills.md`** — register `/we:handoff` (skill 22) with full description.
- **`README.md`** — `/we:handoff` line in "Around the spine"; skill count 21 → 22.
- **`we/CLAUDE.md`** — NEW "Durable Docs Categories" section (Foxy's explicit ask: *"damit sollen die skills docs/plans, docs/retros und docs/handoffs kennen und benutzen, das müsste wohl in claude.md?"*) — declares the three durable directories with owner skills, links to per-skill SKILL.md for conventions.
- **`CLAUDE.md`** (plugin dev) — skill count `# 21 skills` → `# 22 skills`.

### Verification gates

| Phase | Check |
|---|---|
| Skill body | `bash scripts/validate-plugin-structure.sh` reports 22 skills |
| Coach integration | `grep -c '/we:handoff' we/skills/coach/SKILL.md` ≥ 5 (Boot Step 10 + Mode Selection + Suggesting section + pointer + References) |
| Docs | `grep -c '/we:handoff' docs/{skills,workflow}.md README.md we/CLAUDE.md` ≥ 1 per file; "Durable Docs Categories" appears in `we/CLAUDE.md` |
| Tour | "22 skills" in tour HTML; `node --check` full script clean (per `feedback_validate_whole_script.md`) |
| First real run | Smoke test writes `weside-core/docs/handoffs/2026-05-18-phase-7-handoff-skill.md` with full frontmatter + all 9 body sections; privacy guard skipped Companion-mode content |

### Out of scope (explicit)

- **Auto-loading on session start** — CC architecture; SessionStart hooks can't inject context. User must invoke `/we:handoff` manually, or Coach surfaces it.
- **Editing `~/.claude/projects/<repo>/<session>.jsonl`** — that's CC's opaque store; handoff stays a separate file-based artifact.
- **Replacing `/compact`** — complementary, both have a role.
- **Cross-repo handoffs** — one repo per invocation.
- **Automatic ticket creation** — opt-in via `--ticket` flag, off by default.
- **Encryption / per-handoff access control** — repo visibility = access control. Privacy guard keeps personal content out of the file in the first place.
- **Tour station** — operational utility, not methodology pillar.

### Implementation order (one-shot, single commit, plugin v2.30.5 → v2.32.0)

1. `we/skills/handoff/SKILL.md` — frontmatter + Privacy Guard + Boot Protocol + WRITE/LOAD/LIST workflows + template + apply mechanics + examples
2. `we/skills/coach/SKILL.md` — Boot Step 10 + Mode Selection row + "Suggesting `/we:handoff`" section + Disambiguation pointer + References entry
3. Docs refresh — workflow.md (Continuity utilities), skills.md (skill 22 entry), README.md (Around the spine + skill count + tagline), `we/CLAUDE.md` (skill table row + "Durable Docs Categories" section), `CLAUDE.md` (count), `docs/README.md`, `docs/upgrade-paths.md`
4. `docs/concepts/handoff.md` — NEW (parallel to `concepts/retro.md`)
5. `docs/plans/handoff-skill.md` — THIS file
6. `tour/index.html` — skill-count text only, no new station; `node --check` full script
7. `plugin.json` v2.30.5 → v2.32.0
8. Single commit `feat(handoff): /we:handoff skill — durable cross-session continuity (v2.32.0)`, push to main (standing direct-auth)
9. **First real run** — manually execute WRITE workflow against this session, creates `weside-core/docs/handoffs/2026-05-18-phase-7-handoff-skill.md` as first artifact

**Estimated effort:** ~2.5–3 hours end-to-end. Lands as a single commit per Foxy's standing `feedback_consolidate_phases_prs` preference.
