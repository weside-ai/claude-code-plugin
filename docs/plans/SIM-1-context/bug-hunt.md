# SIM-1 bug hunt — round 2, verified against `008ed94`

Scope: `we/hooks/ we/scripts/ we/skills/ we/agents/ we/references/ we/quality/ docs/plan-format.md
docs/skills.md`. `docs/plans/SIM-1-context/` excluded. Findings only — nothing fixed.

**This file replaces its own first version.** That version was written against `a3071d7` and
committed as `3b59e42` ("19 findings closed"). Of those 19, **8 were already fixed** by `bbab94c`
/ `0e7f4f0`, which landed while the review ran, and **5 were measurement errors of mine** — a probe
harness that reused one tmp repo across cases, so files left by an earlier case answered a later
one. Details in *Retracted* below; the fixes made against them were defensive, not wrong, but the
count was inflated.

Everything below was re-run against `008ed94` in a **freshly created armed repo per case**.
Suite: 62/62 green, so none of these is caught today.

**Open: 2 high · 5 medium · 2 low.**

---

## HIGH

### H1 — A correct PR is denied because a *later* command's `--body` overwrites the receipt

`we/hooks/verification_gate.py` — `_pr_verb` returns `rest = argv[i+3:]`, which runs to the end of
argv past every separator, and `_body_of` then loops over all of `rest` with **the last body flag
winning**.

```
gh pr create --body-file good.md && gh pr comment 1 --body 'notes'
```
`good.md` carries a complete receipt; the PR is **denied** (reproduced) — the gate judged the
comment's text and told the author their receipt is missing. This is the expensive direction.
Same mechanism, other way:

```
gh pr create --fill && gh pr comment 1 --body-file receipt.md
```
→ **allowed** (reproduced): the comment's good receipt satisfies the create's missing one.

### H2 — `_pr_verb` stops at the first `gh pr …` and never looks further

`gh pr edit 1 --add-label x && gh pr create --fill` resolves to the `edit`, finds no body flag,
hits the `not seen and verb != "create"` branch → **allowed** (reproduced). Control:
`gh pr create --fill` alone blocks, so this is first-match-wins, not the `--fill` rule.

H1 and H2 are one defect with two faces: `_pr_verb` neither scopes `rest` to the simple command nor
keeps looking after the first match. `_same_command` — added in `3b59e42` for `_written_here` —
is the tool the fix wants.

---

## MEDIUM

### M1 — The gate is skipped whole when the hook's cwd is not a repo

`_repo_root(cwd)` resolves from the **pre-`cd`** payload cwd while the body file resolves
**post-`cd`** (`_cwd_after_cd`). From a non-repo cwd, `cd <armed-repo> && gh pr create --fill`
returns `root=None` and `_refusal` returns before `_required` ever runs (reproduced).
Worktree-per-chunk dispatch puts agents in exactly that position.

### M2 — `cat <<'EOF' | tee pr-body.md` fails open

`_written_here` only recognises a bare `>`/`>>` token, so the `tee` spelling of write-then-create
finds nothing, falls back to a file that does not exist yet, and `seen and body is None` lets the
PR through (reproduced). `3b59e42` fixed the `>`-after-tag ordering; the `| tee` form is the same
root and is still open.

### M3 — A `not-applicable` reason that names the surfaces it lacks is denied, with the wrong message

`_oracles` matches `\bcli\b` / `\bui\b` anywhere on the Oracle line, the reason included.
`**Oracle:** not-applicable — docs only, no CLI and no UI surface.` yields
`{not-applicable, cli, ui}`, fails the `named == {"not-applicable"}` branch, falls through to the
Seed/Asserted check and denies with *"the seed, the assertion or the `Not proven` line are still the
template's placeholders"* (reproduced; the plain-reason control passes).
`we/references/verification.md:29` asks for exactly this kind of reason.

### M4 — One line now contradicts itself about the plugin root

`we/skills/story/SKILL.md:304-306`. `3b59e42` replaced the `<plugin-root>` token with the live-shell
form `WE_ROOT=${CLAUDE_PLUGIN_ROOT:-…}` — but left the two lines under it that say
`${CLAUDE_PLUGIN_ROOT}` "is a skill-text token, not a shell variable: substitute the real path
here". The command now depends on the variable the note says to hand-substitute; following the note
breaks the line.

Related, unchanged by the fix round: with the variable unset in a local checkout, the glob resolves
to the *installed cached* copy — a different `orchestration.py` against a different checkpoint DB
than the tree being edited. The `: "${WE_ROOT:?…}"` guard added in `3b59e42` catches the empty case
but not the wrong-copy case.

### M5 — `develop` Step 4 drops the "Agent teammates only" restriction

`we/references/worker-dispatch.md:73-76` restricts the per-chunk AC-check to Agent teammates ("a
Codex or foreign worker cannot spawn `we:ac-reviewer`"), and `orchestrate/SKILL.md`'s brief carries
the caveat. `we/skills/develop/SKILL.md:135-138` does not — it says run it whenever the brief orders
it or `review.cross` is true. `develop` is what `--engine codex` runs, so a Codex worker following
its own skill attempts a spawn it cannot make.

---

## LOW

### L1 — `bash -c "gh pr create …"` is unseen

The whole command is one shlex token, so `_pr_verb` never sees `gh` (reproduced). The module
docstring already declares one-spelling coverage — filed for completeness, not as a defect.

### L2 — `we/CLAUDE.md:23` still makes `review.cross` the bug-hunt selector

`we/references/worker-dispatch.md:81` and `we/skills/setup/SKILL.md:179` now both say it governs
only the per-chunk AC-check. `we/CLAUDE.md` sits outside the reviewed diff, so this is a pointer for
whoever owns that file, not a finding against this PR.

---

## Retracted from round 1

**Already fixed by `bbab94c` / `0e7f4f0` before I reported them** — real against `a3071d7`, closed
at HEAD: the `plan-format.md` `Assert:` / `Not provable here:` mismatch; the unenforced
`Not proven:` check; the `^### Phase \d+:` colon in `dor-scan.md` and `refine/SKILL.md`; the
`docs/skills.md` ci-review cap wording; `status: blocked`; the `<plugin-root>` token; the
undocumented `Exit criterion:`; the vacuous `isinstance(out, str)` assertion.

**Measurement error — never real.** Re-run one-case-per-repo, all of these behave correctly:

- `cat <<'EOF' > pr-body.md … EOF; gh pr create --body-file pr-body.md` — the redirect *was* seen
  and the heredoc *did* outrank a stale file on disk. My "stale receipt masks a receiptless body"
  claim, reported as the sharpest finding of round 1, was the harness. (`3b59e42` hardened this
  path anyway; the hardening is sound, it just was not fixing a live defect.)
- A fenced `**Seed:**` block passed already; `_FENCE` was not eating legitimate receipts.
- `gh -R owner/repo pr create` and `gh --repo …` are caught.
- `echo $(gh pr create --fill)` is caught.
- `gh pr create --body-file b.md; rm -f b.md` — the trailing `;` does not break the path.

**Lesson for the next round:** every hook case gets its own `tempfile.mkdtemp()`. A shared armed
repo makes an earlier case's leftover file the next case's answer, and the failure mode is a
*confident false positive* — the shape a bug hunt is least able to catch in itself.
