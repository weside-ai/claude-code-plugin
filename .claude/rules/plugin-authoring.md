# Plugin Authoring Rules

These rules keep duplication and cross-file contradictions out of `we/`. They apply when editing
anything under `we/`; the binding contract is `we/AUTHORING.md`, and
`we/references/instruction-authoring.md` holds the limits the budget gate enforces.

The root virtue every rule below serves is **predictability**: a skill exists to make the agent
take the same *process* every run — not to produce the same output. Cost and maintainability
are symptoms of predictability, not rivals to it.

## Contents

- Single owner
- Prose follows the executed artifact
- Naming and vocabulary
- Frontmatter descriptions
- Skill prose discipline
- Invocation cost
- Before every push

## Single owner

Every rule, procedure, schema, or template is defined in **exactly one file** — a skill step, a
`references/*.md`, a role card, or an executed script. Every other place cites it with one
sentence + path (`see references/x.md`). Before writing a block into a second file, check the
existing owners first:

| Fact | Owner |
|---|---|
| the crew process every session loads | `process/L0.md` (rendered by `scripts/render_process.py`) |
| what one role does | `roles/<role>.md` |
| crew file schema and keys | `scripts/crew.py` |
| who merges what (merge table) | `skills/master/SKILL.md` § Close the run |
| worker contract, launch backend, card worker, report | `references/worker-dispatch.md` |
| measured traps of shared trees and CI | `references/session-traps.md` |
| story plan schema and readiness | `references/story-plan.md` (gate: `scripts/ready_gate.py`) |
| epic plan schema · epic skeleton | `references/epic-plan.md` · `skills/epic/references/template.md` |
| where plans are committed | `references/plan-commit.md` |
| reading and moving tickets | `references/ticketing.md` |
| board file, moves, answers, freeze, self-merge window | `docs/board.md` |
| companion launch, pin, binding, writeback | `references/companion-session.md` |
| several humans: crew schema and identity · the ticket verbs between machines | `scripts/crew.py` § Humans · `docs/board.md` § Several humans |
| optimization inbox and ledger | `references/optimization-store.md` |
| privacy before anything leaves the repo | `references/privacy-guard.md` |
| instruction limits and wording | `references/instruction-authoring.md` |

**The one legitimate copy: self-contained briefs.** A brief sent verbatim to a process without
plugin context (the master's worker brief, the refiner's tree limits, the `/we:codex-task` brief) may
carry rules inline — it cannot follow references.

**Rules blocks don't retell steps.** A `## Rules` section at the end of a skill contains ONLY
invariants that are not already stated in the steps. A Rules block that paraphrases the steps is
the start of drift: two places, one behavior, and only one gets updated.

## Prose follows the executed artifact

When documentation and a script disagree, fix the **docs** toward the script — never "align" the
script, that changes behavior. A doc that names a config key the script does not read silently
misleads every project that follows it.

## Naming and vocabulary

- The same term must not mean different things in two skills. New skill → new vocabulary, or
  exactly the same semantics.
- Role names are the crew's role keys (`product`, `architecture`, `acceptance`, `machinery`,
  `coordinator`, `escalation`, `hr`, `security`) or their tokens in the L0, never a person's name.
- **Leading words.** The design vocabulary — `seam`, `tracer bullet`, `tight` (loop),
  `deep`/`shallow` (module), `deletion test`.
  Use exactly these words wherever the concept appears; never substitute synonyms
  ("boundary", "vertical slice", "fast feedback"). A leading word recruits priors the model
  already holds — one word does the work of a sentence, but only if every file uses the same one.
- `subagent_type` is always plugin-namespaced: `we:dev-medium`, never bare `dev-medium`.
- A plugin command never shares a name with a skill directory (the dispatch-loop anti-pattern;
  CI rejects it).

## Frontmatter descriptions

Skill `description:` frontmatter is always-on context in every session's skill list. The limit is
the budget gate's (`we/AUTHORING.md` § Shape of a skill): what the skill does + the trigger
phrases. Routing logic ("use X instead when Y") belongs in the body, not the description.

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
- **Today, not history.** Describe what the code does now; a decision may carry who and when,
  a version number or "before vX" never.

## Invocation cost

Every skill pays one of two costs: model-invocable skills pay **context load** (their
description sits in every session), user-only skills (`disable-model-invocation: true`) pay
**cognitive load** (the user must remember they exist). Nearly all skills stay model-invocable:
the plugin leans on natural-language triggers ("retro", "where am I", "diagnose this") and on
skill-to-skill dispatch (setup→council, master→develop), both of which require model invocation.
Revisit per skill only when a skill gains a description with no trigger phrases.

## Before every push

Run the checks in `AGENTS.md` § Checks before a commit. `python3 scripts/validate-consistency.py`
rejects (its docstring lists every check): command/skill name collisions; dead
`references/*.md`, `/we:*`, `we:*` and `subagent_type` mentions; `plugin.json` userConfig options
that no file reads; a skill listing over its budget; **indiscretions** — credentials, personal
email addresses, developer home paths, internal hosts, Supabase project refs, k8s namespaces or
test accounts in any tracked file; `agents.*` config keys missing from `/we:setup`'s schema block
and worker-launch placeholders out of step with `worker-dispatch.md`; a lens skill or default lens
without its agent; installer `VERDICT:` lines `/we:setup` branches on; the gate hook's `files:`
filters out of step with the ones `/we:setup` installs; retired paths and terms; `.weside/orchestrate.md` sections the template lacks;
a skill naming its author's own owner; a second plugin resolver. The indiscretion check exists
because this repo is public: a leak is not a lint finding, it is a rotation. Write placeholders
(`/home/user/`, `os.environ["X"]` with no default), never a real value. **When you find a new
cross-file error class, add a check there — don't just fix the instance.**
