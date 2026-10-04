# Authoring contract for we 7.0

Every file in `we/` is here on purpose. This contract says what earns a line. Read it before you
write or port a skill, agent, hook or reference.

## The rule for every line

A line stays only if a session would act worse without it. Four kinds of line qualify:

1. A fact the model cannot derive from the repo or from Claude Code itself: a file layout the skill
   writes, a state format, a verb's contract with another verb.
2. A decision the product owner made, with its date.
3. A measured trap: something the Opus 5.5 bench or the transcripts showed going wrong, stated as
   the fact and the fix, never as the story.
4. A pointer to the gate, script or built-in that enforces or does the thing.

Everything else goes: generic engineering advice, restated Claude Code behaviour, motivational or
emphatic wording (capitals, "never ever", ⛔), duplicated text across skills, run histories.

## Shape of a skill

- Frontmatter `description` states what the verb does and its triggers, at most ~250 characters.
- The first five lines tell a reader who reads nothing else how to act correctly.
- Every line reads on its own: no "see above", no pronoun that crosses a paragraph.
- One home per fact. A fact two skills need lives in `references/` and both point at it.
- Target: under 150 lines per `SKILL.md`. Longer needs a one-line reason at the top.
- English.

## Built-ins first

Where Claude Code does the job, point at it instead of re-implementing it:

| Need | Use |
|---|---|
| Worker isolation | `Agent` with `isolation: "worktree"` |
| Worker effort | `subagent_type: "we:dev-medium"` (default) or `"we:dev-high"` (Lead states the reason) |
| Broad read-only search | `subagent_type: "we:explore-medium"`; the built-in `Explore` inherits the caller's effort |
| Waiting for CI or a background job | a background command with a wait condition (`scripts/watch-pr-checks.sh <PR>`, `gh run watch <id> --exit-status`), never a sleep loop; `Monitor` only for waits under 30 min |
| Task checklist inside a long run | a checklist in the PR body or plan (the task tools are absent in `claude -p`) |
| Bug review before the first push | the CI review on the PR; locally only for money, auth, tenant isolation or a migration: Skill tool `code-review` with `args: "high <worktree path>"` (inside a subagent always via the Skill tool; a slash command in a prompt is not proven to run it) |
| Cross-repo work that edits the other repo | a native session there (`claude --bg` in that directory) steered with `SendMessage` |
| Cross-repo reading | `--add-dir` with `additionalDirectoriesForClaudeMd` |
| Session continuation | `/resume`, `/fork`, `/recap` — `handoff` only for a cross-session restart |

## Measured facts a skill must respect (Opus 5.5 bench, 26.–27.09.2026)

- Default effort is `medium`. `high` pays off for a promise that must hold across several code
  paths, for transactions, money or idempotency, for a fix routing around a fragile path, and for a
  second attempt after a failed worker. A clearly bounded single fix gains nothing from `high`.
- Implementation never runs on Sonnet; Haiku or Sonnet only for mechanical chunks the Lead names.
- Parallel workers saved no net time in 48 of 54 past orchestrate runs: waves ran in series and
  integration ate the gain. One implementer is the normal case; parallel only for disjoint files
  with a fixed contract.
- The Lead produced more output tokens than all workers together. Keep the Lead's own reading and
  re-checking small; delegate reading.
- The most frequent loss of autonomy is ending a turn with an announcement instead of the next
  action. Skills that run long say which stops are wanted (nothing can move without the user, or a
  protected action) and that every other status note goes into the same message as the next tool
  call.
- The most frequent correction is a wrong assumption about the environment or an earlier decision.
  Skills read the repo's instruction files and decision records before assuming.
- Claude Review (Opus 5.5 `medium`) is the required review gate; Codex is advisory and ends with the
  subscription.

## Porting from v6

For each v6 file: list its units, decide per unit (keep · shorten · replace by built-in · drop) with
a reason, write the v7 file from those decisions. Record the decisions in the port note the Lead
asks for. Do not copy a v6 file and trim it; start from the decisions.

## Testing a revised skill

Table-top first: two or three Opus agents trace every tool call of the skill against concrete world states
(no execution) and list defects adversarially; repeat until the verdict stops moving. Then one live run.
