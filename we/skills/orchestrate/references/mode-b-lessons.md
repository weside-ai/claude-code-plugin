# Mode B — Hard-Won Lessons (read before dispatching chunks)

Field notes from real lead-integrated phase-dispatch runs. The Rules section in `SKILL.md` summarises these; this file carries the full reasoning. Read it whenever you run Mode B.

## Sequencing the chunks

- **The parallelism is usually less than it looks — run the discriminating check before fanning out.**
  Ask of each "disjoint" chunk: *can it land touching only its own files, with zero edits to any
  shared file the other chunks also need?* The trap is a shared file every phase has to make real —
  not just the named interface you froze, but any common helper the phases fill in. If two chunks
  would both edit it, they are **not** disjoint; that shared work is **another serial foundation
  chunk**, done once before the per-unit chunks parallelize. Found the hard way: two units looked
  independent but both had to fill the same shared scaffolding — parallel dispatch would have collided
  at integration. Rule of thumb: a chunk that *makes shared scaffolding real* (freezes a contract every
  later chunk consumes) is **foundation-completion → serial-first**. You cannot race a chunk against
  the thing it depends on becoming real. The real parallelism appears late — in the per-unit wiring,
  once the shared scaffolding is frozen.
- **There is often more than one shared layer — re-run the check at *every* wave boundary, not once.**
  On the real run two distinct shared layers surfaced (a shared dispatch seam *and* a shared set of
  gate-stage files); each needed its own serial freeze-chunk before the per-unit chunks could
  parallelize. Don't assume one foundation chunk clears the way. Before each parallel wave, re-ask the
  discriminating question against what's *still* unfrozen; collapse to serial whenever the answer is no.
- **Worktree hygiene is non-negotiable.** Each teammate works in its **own** worktree branched off the
  integration branch (so it carries the prior integrated chunks); the Lead integrates in a **dedicated
  lead worktree**; the Lead **never** flips the *main* worktree's branch. Flipping the shared main
  worktree between branches mid-orchestration lands commits on the wrong branch and lets a stray rebase
  rewrite a teammate's pushed work — a real, repeated failure mode. The main worktree stays on the
  default branch, untouched, for the whole run.

## Writing the chunk brief

- **Default builders to the mid-tier model; reserve the top tier for a deliberately-hard chunk.** Routine
  implementation chunks run fine on the faster/cheaper model (e.g. Sonnet); spend the top tier (e.g. Opus)
  only where the Lead can name *why* it's hard — delicate ordering, a boss-fight teardown, a contract
  freeze every later chunk depends on. Reflexively spawning the top tier for every chunk is the wrong
  cost/fit. Make the escalation an explicit, justified per-chunk choice, not the default.
- **Invite the builder to surface a fork *before* it pins behaviour.** The brief should say: if you hit a
  real design fork (which transport, which failure semantics, which seam), send it to the Lead *before*
  writing the characterization — so the Lead's call shapes the pins, instead of forcing a rework after.
  The best builders do this unprompted; ask for it explicitly so the rest do too.
- **A characterization pin is for behaviour that *already exists*, not a gain the migration adds.** Tell
  builders to pin the current behaviour (green on the unmodified code), and to flag — not pin — any
  property the refactor newly *introduces* (it would be red-on-old-code, so it isn't characterization).
  Confusing "preserve what's there" with "the new thing we're adding" produces a pin that can't go green
  first; a sharp builder will push back on a brief that asks for it, and they're right.

## Reviewing a chunk (the Lead's core act)

- **"All green" is the start of review, not the end.** When a builder honestly surfaces a decision it
  made at a fork (the good ones do — invite it in the brief), evaluate it against the **acceptance
  criterion**, not the test status. Green tests pin what they cover; the edge that breaks the AC is
  usually the one no pin covers (e.g. a happy-path net that silently changes an error-path contract).
  An over-claimed safety net — a characterization docstring claiming more than it pins — is worse than
  an honest gap, because it reads as covered when it isn't.
- **Moving a behaviour's locus is an allowed, explicit characterization change.** When a refactor moves
  *where* a behaviour is produced — same observable outcome, different internal actor — the Lead may
  explicitly approve rewriting the pin to the new locus, noted in the commit. That is reviewed and
  intentional, categorically different from silently weakening an assertion to make a build pass: the
  test still proves the observable behaviour; only the thing it watches moved.
- **Validate the *integrated* state broadly — a chunk's own green is scoped to its files.** Each teammate
  runs narrow checks (its files, its tests). A foundation chunk that changed a shared contract can leave
  a latent error in a *sibling* file no chunk's narrow gate covers — it only surfaces when the Lead runs
  a broad check on the merged tree. So the Lead's integration step re-runs the type-checker/tests at full
  scope after each merge, not just the chunk's slice. (Real run: a contract change in one foundation chunk
  left a type error in an unrelated adapter; every chunk was green, the integrated branch was not.)
- **The Lead owns cross-cutting integration glue.** When that broad check finds a latent error in a file
  outside every chunk's scope, the Lead fixes it *itself* as a small, clearly-labelled integration commit
  (delete the dead code, the one-line conformance fix) — it does not expand a teammate's scope to reach
  into a file it was told to leave alone. Keep the glue commits separate and named so the history stays
  honest about what was chunk work and what was integration.
- **Watch your own working directory when integrating across worktrees.** The Lead juggles several
  worktrees; a mid-command `cd` into the wrong one makes a validation run silently test the *wrong* tree
  (it passes, but it proved nothing about the integration branch). Re-confirm the worktree root before
  trusting a green. A green from the wrong directory is worse than a red.
- **A migration chunk's end-of-change QS MUST run a REAL-DB alembic roundtrip — the Lead owns it.** A
  teammate in a throwaway worktree usually has **no database**, so it can only *defer* the
  `alembic upgrade → downgrade → upgrade` roundtrip — that deferral is NOT verification. For any chunk
  that adds or edits a migration, the Lead runs the real roundtrip against the dev DB at integration. A
  real bug slipped past once because the teammate deferred it and the Lead trusted "all green": a
  partial `seed_upsert(rows=[{"id":44,"is_active":False}], …)` — INSERT…ON CONFLICT DO UPDATE — fired its
  INSERT fallback when id 44 was absent and violated NOT NULL. Only the Lead's actual roundtrip caught it.
- **A chunk whose tests need a DB or the JS toolchain can't run them in a fresh worktree — the Lead's QS
  owns the real test pass.** Throwaway teammate worktrees have no `node_modules` / poetry venv, so a
  teammate deferring frontend jest or backend pytest is fine — but the Lead MUST then actually run them at
  integration. Set that expectation in the brief. Symlink the main worktree's root `node_modules` into the
  integration worktree (instant) instead of a ~1GB `yarn install`.
- **Run the WHOLE affected test set at integration, not just the file the builder touched.** A builder
  that adds a required field to a schema updates *its* unit test, but the same object is often constructed
  from mocks in sibling **integration** tests that won't set the new field — they fail (e.g. a pydantic
  `MagicMock`-not-a-string error) only when actually run. The Lead's QS must run unit AND integration for
  every module the change touches (`pytest tests/unit/... tests/integration/...`), not the one unit file
  the builder reported green.
- **Integration/merge commits need an allowed conventional-commit type.** The commitizen hook rejects
  `merge:` (not an allowed type). Use e.g. `chore({TICKET}): integrate <phase> …` for the Lead's
  `git merge` integration commits.
- **A full regen of generated specs can clash with the formatter hook.** Before committing a regenerated
  OpenAPI/shared-types spec, check which generated files are actually CI-gated, keep the spec diff minimal,
  and note that a generator-vs-prettier format clash (e.g. lint-staged collapsing the generator's expanded
  JSON) may require committing the generated spec with `--no-verify` to preserve the generator's output.
