# Plugin Authoring Rules

Distilled from the July 2026 consolidation (v2.66–v3.3), which removed 17 duplication clusters
and 12 real cross-file contradictions that had accumulated over ~60 releases. These rules keep
those error classes from coming back. They apply when editing anything under `we/`.

## Single owner

Every rule, procedure, schema, or template is defined in **exactly one file** — a skill step, a
`references/*.md`, `quality/*.md`, or an executed script. Every other place cites it with one
sentence + path (`see references/x.md`). Before writing a block into a second file, check the
existing owners first: `dor-scan`, `ticketing` (incl. transition procedure), `worker-dispatch`
(cross-review matrix + model tiers), `po-altitude` (epic/saga skeleton), `council-deliberation`,
`mirror-block`, `agent-teams` (env flag + teardown), `privacy-guard`, `companion-voice`,
`quality/dor.md` + `dod.md`.

**The one legitimate copy: self-contained briefs.** Worker/refiner/chunk briefs that are sent
verbatim to processes without plugin context (orchestrate's Worker-Brief, codex-dispatch's chunk
brief, the foreign-engine brief) may carry rules inline — they cannot follow references.

**Rules blocks don't retell steps.** A `## Rules` section at the end of a skill contains ONLY
invariants that are not already stated in the steps. A Rules block that paraphrases the steps is
the start of drift: two places, one behavior, and only one gets updated. (orchestrate once
carried 72 lines of step paraphrase.)

## Prose follows the executed artifact

When documentation and a script disagree, fix the **docs** toward the script — never "align" the
script, that changes behavior. (Lesson: two files documented the config key
`primitive_detectors_extra` while the script read `primitive_detectors`; projects following the
schema doc were silently ignored.)

## Naming and vocabulary

- The same term must not mean different things in two skills. (Lesson: "Mode A/B" meant
  sequential-vs-parallel in build but Story-vs-phase dispatch in orchestrate — build's modes are
  now "inline"/"fan-out".) New skill → new vocabulary, or exactly the same semantics.
- `subagent_type` is always plugin-namespaced: `we:doc-architect`, never bare `doc-architect`.
- Never create a command in `we/commands/` with the same name as a skill directory — the
  documented dispatch-loop anti-pattern (CI now rejects it).

## Frontmatter descriptions

Skill `description:` frontmatter is always-on context in every session's skill list. Keep it
≤ ~400 bytes: what the skill does + the trigger phrases. Routing logic ("use X instead when Y")
belongs in the body, not the description.

## Before every push

Run `python3 scripts/validate-consistency.py` (plus the frontmatter/structure validators — all
run in CI too). It rejects: STORY_PHASES drift between `orchestration.py` and the markdown,
command/skill name collisions, dead `references/*.md` / `/we:*` / `subagent_type` mentions, and
`plugin.json` userConfig options that no file reads. **When you find a new cross-file error
class, add a check there — don't just fix the instance.**
