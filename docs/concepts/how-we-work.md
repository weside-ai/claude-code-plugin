# How We Work — the canonical grounding manifest

This is the **single canonical index** of what "how we work" means for this plugin: the APO
method, the altitudes, the pipeline, and the skill catalog. It is an **index, not a summary** —
every entry points to a living doc and names the compact part to load. The content stays in the
living docs, so this manifest **cannot drift** from them.

`/we:coach` and `/we:retro` both load this at boot, so both reason from the same, always-current
picture of how we work — without the user having to explain anything.

## How to use this manifest

Load the **named section** of each source below — not the full file. The point is to know the
method cold while staying within a tight token budget. Do **not** read full skill bodies at boot;
the skill catalog (descriptions) tells you *what* each skill does and *when*, which is enough to
know where to dig.

## Canonical sources

| Source | Load this part | Why it grounds you |
|--------|----------------|--------------------|
| [`../../we/CLAUDE.md`](../../we/CLAUDE.md) | §"What is Agentic Product Ownership?", §"Pipeline Overview", §"Skills" | the APO model + the full skill/command/agent list — the spine of the method |
| [`meetings.md`](meetings.md) | §"The four altitudes" + the naming/storage table | Vision → Saga → Epic → Story, and the Solo-vs-Meet split at each |
| [`../workflow.md`](../workflow.md) | §"The big picture" + the Phase 1–4 headers | the end-to-end pipeline: Plan → Build → Deliver → Retro, and where each skill sits |
| [`../skills.md`](../skills.md) | the per-skill `###` entries (tagline + "when to use") | the catalog — what every `/we:*` does and when to reach for it |
| [`../../we/quality/dor.md`](../../we/quality/dor.md) · [`../../we/quality/dod.md`](../../we/quality/dod.md) | the checklists | the Definition of Ready / Done gates the pipeline enforces |

## What this is NOT

- Not a tutorial — for learning by doing, see [`../getting-started.md`](../getting-started.md).
- Not a summary to maintain — if the method changes, the living docs above change; this index
  only updates when a doc moves or a new canonical source is added.

## References

- Consumers: `we/skills/coach/SKILL.md` (boot grounding + Scrum-Master front door),
  `we/skills/retro/SKILL.md` (boot grounding for the improvement scan).
