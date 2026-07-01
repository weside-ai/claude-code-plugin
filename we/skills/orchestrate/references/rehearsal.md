# Rehearsal mode (`--rehearsal`)

Run the complete pipeline **without a real epic/story/code** — to shake out where the skills
stumble and optimise them. Repeatable via the built-in `/loop` skill
(`/loop /we:orchestrate FIXTURE --rehearsal`).

1. Set up a throwaway repo (or worktree) and copy the committed fixture template
   `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/references/fixture-story.md` into it as
   `docs/plans/FIXTURE-story.md`. Its AC is trivial but **real** (a pure `rehearsal_noop() -> 42`
   with a test) so the real review/test/PR steps have a genuine diff to chew on — a fully mocked
   no-op would short-circuit the skills and prove nothing.
2. Dispatch exactly one builder for the fixture, but instruct it: target a **throwaway worktree**,
   **plan-only ticketing** (no Jira transitions), and **no real PR** — create a draft on a scratch
   branch and delete it on teardown, or stop before push.
3. Run the **real** Step 1–8 build logic so genuine skill bugs surface.
4. Append the friction points (which step stumbled, the exact error) to a rehearsal log:
   `docs/retros/YYYY-MM-DD-orchestrate-rehearsal.md` (repo-relative, under the story repo root).
5. Tear down the builder (shutdown message → verify → `TaskStop` fallback), delete the scratch
   worktree/branch. Loop to repeat.

This is the lab for the broader skill clean-up: each iteration → `plugin-dev:skill-reviewer` /
`plugin-validator` against the skill that stumbled → targeted fix → re-loop.

## `--refine-ahead` P3 go/no-go (the refiner-teammate gate)

Before enabling the autonomous refiner lane (P3, see `refine-ahead-p3.md`) on real work, prove it in
rehearsal. Stage a **two-story fixture** into the throwaway repo's `docs/plans/`: copy
`fixture-story.md` → `FIXTURE-story.md` (already refined → `ready`) **and**
`fixture-refinable-story.md` → `FIXTURE2-story.md` (unrefined, `depends_on: [FIXTURE]` → `refinable`).
Then run `/we:orchestrate rehearsal --rehearsal --refine-ahead`. The go/no-go question:
**does the refiner-teammate write a DoR-passing `docs/plans/{TICKET}-story.md` (the Lead's `story
ready` shows it left `refinable`) without stalling in plan mode, under the session's permission mode?**

- **GO** → the refiner lane is safe to enable on real epics.
- **NO-GO** (stalls at ExitPlanMode, or its output fails the DoR scan, or teammate Bash/Write is denied)
  → leave P3 disabled; P2's Lead-interactive lane already delivers the build/refine overlap. Log the
  exact failure to the rehearsal log so the brief can be tuned and re-looped.
