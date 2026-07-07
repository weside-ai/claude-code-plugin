# Plugin Authoring Rules

Distilled from the July 2026 consolidation (v2.66–v3.3), which removed 17 duplication clusters
and 12 real cross-file contradictions that had accumulated over ~60 releases, and extended in
v3.5.0 with writing principles adapted from Matt Pocock's skills (MIT). These rules keep
those error classes from coming back. They apply when editing anything under `we/`.

The root virtue every rule below serves is **predictability**: a skill exists to make the agent
take the same *process* every run — not to produce the same output. Cost and maintainability
are symptoms of predictability, not rivals to it.

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
- **Leading words.** The design vocabulary — `seam`, `tracer bullet`, `tight` (loop),
  `deep`/`shallow` (module), `deletion test` — is owned by `we/references/design-vocabulary.md`.
  Use exactly these words wherever the concept appears; never substitute synonyms
  ("boundary", "vertical slice", "fast feedback"). A leading word recruits priors the model
  already holds — one word does the work of a sentence, but only if every file uses the same one.
- `subagent_type` is always plugin-namespaced: `we:doc-architect`, never bare `doc-architect`.
- Never create a command in `we/commands/` with the same name as a skill directory — the
  documented dispatch-loop anti-pattern (CI now rejects it).

## Frontmatter descriptions

Skill `description:` frontmatter is always-on context in every session's skill list. Keep it
≤ ~400 bytes: what the skill does + the trigger phrases. Routing logic ("use X instead when Y")
belongs in the body, not the description.

- **Front-load the leading word.** The first word or phrase names the action or artifact
  ("Convene a council…", "Disciplined diagnosis loop…"), then the triggers, quoted verbatim.
- **One trigger per branch.** Each quoted phrase must reach a distinct branch of the skill.
  Synonyms that rename a single branch are duplication — cut them.

## Skill prose discipline

- **Pair every negation.** "Don't X" alone steers by prohibition and backfires; write the
  positive action next to it ("Don't mock internal collaborators — mock at system boundaries
  only"). A bare prohibition is allowed only when no positive form exists.
- **No no-ops.** A line the model already obeys by default ("be thorough", "consider edge
  cases") pays context load to say nothing. Cut it — or, if it must steer, replace it with a
  stronger word that actually changes behavior (*relentless*, *aggressive*).
- **Completion criteria are checkable.** A phase ends with `- [ ]` items the agent can verify
  (can it tell done from not-done?), not with prose like "when everything works". Where it
  matters, the checklist is exhaustive.
- **Quality judgments come as good/bad pairs.** Whenever a skill teaches what "good" looks
  like (a test, a ticket, a brief), show a contrasting pair — never an isolated recommendation
  or an adjective.

## Invocation cost

Every skill pays one of two costs: model-invocable skills pay **context load** (their
description sits in every session), user-only skills (`disable-model-invocation: true`) pay
**cognitive load** (the user must remember they exist). Decision note (v3.5.0 audit): we keep
nearly all skills model-invocable — the plugin leans on natural-language triggers ("retro",
"where am I", "diagnose this") and on skill-to-skill dispatch (meet→council, setup→onboarding,
orchestrate→develop), both of which require model invocation. Revisit per skill only when a
skill gains a description with no trigger phrases.

## Before every push

Run `python3 scripts/validate-consistency.py` (plus the frontmatter/structure validators — all
run in CI too). It rejects: STORY_PHASES drift between `orchestration.py` and the markdown,
command/skill name collisions, dead `references/*.md` / `/we:*` / `subagent_type` mentions, and
`plugin.json` userConfig options that no file reads. **When you find a new cross-file error
class, add a check there — don't just fix the instance.**
