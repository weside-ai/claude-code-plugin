---
type: simulation-report
chunk: gates
scenario: C — receipt in the plan, not in the PR body
round: 1
grade: 2
---
# Round 1 · Scenario C

## Trace

I am `we:pr-creator`, dispatched with `Create PR for TICKET-101`, entering at Step 6.

1. **Step 6 — `gh` availability.** `Bash: gh auth status`. Hook: `tool_name == "Bash"`, `"gh" in command` true, `"pr" in command` false → `_receipt_missing` returns False at hook:122. Allowed. Result: authenticated. I do **not** take the Step 6 escape hatch; Steps 7–8 run.

2. **Step 5 leftovers → body assembly.** I read the ticket summary and `git log --oneline main..HEAD` for the commit subjects, and assemble Summary / Changes / Test Plan / `TICKET-101`. Nothing in `pr-creator.md` sends me to `docs/plans/TICKET-101-story.md`, so I never open the plan and the receipt sitting in its `## Verification` section is not copied. **This is the scenario's actual defect, and it happens before any hook runs.**

3. **Step 7, attempt 1 — inline body via command-substituted heredoc.** Tool call I would make:

   ```
   gh pr create --title "TICKET-101: Widgets" --body "$(cat <<'EOF'
   ## Summary
   …
   ## Changes
   …
   ## Test Plan
   …
   TICKET-101
   EOF
   )"
   ```

   Hook: prefilter passes. `_body_of` → `shlex.split` yields `['gh','pr','create','--title','TICKET-101: Widgets','--body', "$(cat <<'EOF'\n## Summary\n…\nEOF\n)"]`. Match at index 0, `rest` from index 3, `--body` branch (hook:96-97) takes the **next token verbatim**. Resolved body is the *unexpanded source text of the command substitution* — `$(cat <<'EOF'` … `EOF` … `)` with the outer double quotes stripped — not the string `gh` would receive. It happens to carry my body text only because the heredoc is inline in the same command. No `## Verification`, no oracle word → **DENIED**.

4. **Reading the denial.** The message is: *"This PR claims work is done without saying how that was observed. Unit tests do not count…"* followed by `_HINT`: *"Add a `## Verification` block to the PR body, then retry:"* and a four-field template. It says **Add**. It never names `docs/plans/TICKET-101-story.md`, never says the receipt already exists, never says *copy*. Nothing in `pr-creator.md` fills that gap either. The message's own gravity is toward filling the template from what I have in context — the commit subjects and `tests/api/test_widgets.py` — i.e. toward inventing a receipt for a verification I did not run.

5. **Attempt 2 (what I do).** I go looking for a real receipt rather than authoring one: `Read docs/plans/TICKET-101-story.md`, find the complete block (oracle `cli`, seed `weside widgets create --json`, asserted `201 + id`, not proven: push + device geometry), and copy it verbatim. I switch to a file to stop the substitution problem recurring:
   - `Bash: cat > pr-body-TICKET-101.md <<'EOF' … EOF` (worktree-local scratch). Hook: the body prose contains `gh` and `pr` as *substrings* ("through", "proven"), so the prefilter passes; `_body_of` finds no bare `gh` token followed by `pr create` → `(False, None)` → allowed.
   - `Bash: gh pr create --title "TICKET-101: Widgets" --body-file pr-body-TICKET-101.md`. Hook: `--body-file` branch (hook:100-105) reads the file, `_HEADING` and `_ORACLE` both match → allowed. PR opens.

6. **Step 8.** Jira comment with the PR link, transition → In Review, soft-fail on rejection.

7. **Step 9.** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint TICKET-101 pr_created`. Hook: `"gh"` not in the command → returns at hook:122. Allowed.

**Two attempts.** But the count is not the finding: a run that pasted the hint's template back with its placeholders unfilled *also* takes two attempts and *also* passes (verified — see Defect 1). The hook cannot tell my copied receipt from a fabricated one, so "how many retries" is not the discriminator; "did the message send me to the plan" is, and it did not.

## The false positive, explained from the code

The live denial was a heredoc write, shape:

```
cd <worktree> && mkdir -p <dir> && cat > <dir>/world.md <<'WEOF'
… document text containing a fenced example with bare `gh pr create … --title … --body …` …
WEOF
```

**Armed on every Bash call.** `we/hooks/hooks.json:23-32` registers the hook as
> `"matcher": "Bash"`

with no command narrowing whatsoever, so `_body_of` parses **every** Bash invocation in the session — which is how a `cat > … <<'WEOF'` documentation write reached a PR-receipt parser at all. The parser being loose is defect 2; the parser being loose *and* armed on every Bash call is the width.

**Function:** `_body_of` (hook:75-113), reached because `_receipt_missing`'s prefilter (hook:121-122) is a plain substring test — `"gh" in command` and `"pr" in command` — which nearly all English prose passes ("through", "proven").

**Tokens:** `shlex.split` (hook:82) has no concept of a shell. It is not heredoc-aware, not redirection-aware, not command-position-aware. Verified output for the shape above:

```
['cd','/w','&&','mkdir','-p','d','&&','cat','>','d/world.md','<<WEOF','Example:',
 '```bash','gh','pr','create','--title','TICKET-101: X','--body','$(cat body.md)','```','WEOF']
```

The `<<'WEOF'` redirection becomes the ordinary word `<<WEOF`, and **the entire document body is tokenized as argv**.

**Branch:** the head-finding loop (hook:87-88) — `if tok == "gh" and argv[i+1:i+3] in (["pr","create"], ["pr","edit"])` — matches at index 13, *inside the document*. `rest = argv[i+3:]` is the remainder of the document. The `--body` branch (hook:96-97) then takes the following token.

**Resolved body:** `$(cat body.md)` — a fragment of prose I was writing to disk. No `## Verification`, so `_receipt_missing` returns True at hook:133 and the write is denied with the full receipt-missing message.

**Width of the class.** Two conditions must hold together: (a) the three words `gh pr create` (or `gh pr edit`) appear **unquoted and space-separated**, and (b) a later **unquoted** token is `--body`, `-b`, `--body=…`, `--body-file` or `--body-file=…`.

What that includes and excludes, verified:
- A markdown code span is **safe**: `` `gh pr create` `` splits to `['`gh','pr','create`']` — the token is `` `gh ``, not `gh`. No match.
- A quoted argument is **safe**: `printf '%s' "run: gh pr create"` is one token. No match.
- A **heredoc body is the dominant vector**, because it is the only common place where prose reaches `shlex` unquoted. A fenced ```` ```bash ```` block inside a heredoc is exactly condition (a).
- `-b` widens (b) far past `gh`: any heredoc mentioning `gh pr create` followed anywhere by `git checkout -b`, `a start -b`, `grep -b`, or the literal `-b` in a second example.

So the everyday commands denied in a session that **writes documentation about PRs**: `cat > <file> <<'EOF'` for a rule, a plan, a runbook, a retro, a simulation world file, or a test fixture whose text shows a `gh pr create` example unfenced-quoted; the same via `tee <<EOF`; a `python3 - <<'PY'` script embedding such an example. This round's own world state and this report are both in that class — the gate denies its own documentation, and it does so with a message about verification receipts, which is maximally misleading about the cause.

**The smallest fix, as a rule (two required parts):**

- **(a) Position + heredoc, in the hook.** A `gh` token counts only in **command position**: index 0, or immediately preceded by a separator token (`&&`, `||`, `;`, `|`, `&`, `(`, `{`, `then`, `do`, `else`). And **strip every heredoc body before splitting** — `re.sub(r"<<-?\s*(['\"]?)(\w+)\1.*?^\2$", "", command, flags=re.S | re.M)` — since no real `gh pr create` ever lives inside one. Both are additive constraints: they can only ever *reduce* matches, so no real PR creation starts passing. Verified against both directions: the observed heredoc write now yields `(False, None)`, and `git push && gh pr create --title "T" --body-file b.md` still yields `(True, ['--title','T','--body-file','b.md'])`. The lazy `.*?` takes the first terminator, an unmatched delimiter simply fails to strip (fail-open, as the docstring promises), and over-stripping cannot hide a real `gh pr create` because one never lives inside a heredoc.
- **(b) `--body-file` mandated, in `pr-creator.md` Step 7.** Part (a) is **not safe alone.** Today a *correctly copied* receipt inside `--body "$(cat <<'EOF' … EOF)"` passes only by accident — the receipt text survives in the unexpanded substitution source that `_body_of` returns. Strip heredocs and that same correct PR is denied. The hook cannot expand a substitution and must not try (hook:11-12), so the fix has to move the body to a file the hook can read. Ship (a) and (b) together or ship neither.

## Which gate stops what, with which message

| Attempt | Gate | Outcome | Message |
|---|---|---|---|
| Step 6 `gh auth status` | hook prefilter, hook:122 (`"pr"` absent) | pass | — |
| Attempt 1, `--body "$(cat <<'EOF' … )"`, no receipt | `_body_of` resolves the substitution *source*; no heading | **deny** | *"This PR claims work is done without saying how that was observed…"* + `_HINT` |
| `cat > .git/pr-body-…md <<'EOF'` (my body has no bare `gh pr create`) | `_body_of` → `(False, None)`, hook:127 | pass | — |
| Attempt 2, `--body-file …` with the copied receipt | `_HEADING` + `_ORACLE` both match, hook:133 | pass | — |
| **Not stopped:** `gh pr create --fill`, or with no `--body` at all (editor body) | `body is None` → hook:127 | **pass** | — |
| **Not stopped:** `gh pr create --body-file typo.md` | hook:105/111 → `(True, None)` → hook:127 | **pass** | — |
| **Not stopped:** the hint's own template pasted back unfilled | `_ORACLE` matches the *menu*, hook:133 | **pass** | — |
| **Wrongly stopped:** any heredoc writing docs about PRs | `_body_of`, hook:82/87 | **deny**, receipt message | as above |

Read together: the gate denies documentation writes and the most obvious correct idiom, while the two most idiomatic `gh` invocations (`--fill`, editor body) walk straight through. It is not a tight gate that occasionally misfires.

## Defects

1. **The gate's own remedy text satisfies the gate — a total false negative.** `we/hooks/verification_gate.py:34-47`:
   > Add a `## Verification` block to the PR body, then retry:` … `**Oracle:** cli | ui | substitute | not-applicable` … `**Seed:** <copy-pasteable command that puts the system in the asserted state>

   Verified: pasting that template verbatim, placeholders unfilled, passes both regexes. `_ORACLE` (`:29-32`) matches vocabulary, not a filled field — the menu line `cli | ui | substitute | not-applicable` scores two independent hits (`oracle`, `substitut`) *from having made no choice*. So the denied model's cheapest path out is to echo the denial back, and the artifact the gate exists to protect is the artifact the gate teaches you to fabricate. **Smallest fix:** replace lines 34-47 with one line — ``"The receipt already exists: copy the `## Verification` block from the story plan (`docs/plans/{TICKET}-story.md`) into the PR body verbatim. If the plan has none, verification did not happen — go do it; do not author a block here. Contract: references/verification.md."`` One edit closes defects 1 and 4 and cuts 13 lines (see Cuttable 1). **Severity: highest — this is the one defect that makes the gate non-binding.**

2. **`_body_of` scans the whole command string, heredoc bodies included.** `we/hooks/verification_gate.py:82`:
   > `argv = shlex.split(command)`

   and `:87-88`:
   > for i, tok in enumerate(argv):` / `    if tok == "gh" and argv[i + 1 : i + 3] in (["pr", "create"], ["pr", "edit"]):

   Concrete failure: the observed denial of a `cat > … <<'WEOF'` documentation write, resolved body `$(cat body.md)`. Fix: part (a) above (command-position check + heredoc strip). Note the comment at `:86` — *"a compound command may have prefixes"* — is the intent that was implemented as "match anywhere", which is where the bug entered.

3. **`--body` takes the token verbatim, so a command substitution is never the real body.** `we/hooks/verification_gate.py:96-97`:
   > if tok in ("--body", "-b") and j + 1 < len(rest):` / `    body = rest[j + 1]

   `gh pr create --body "$(cat body.md)"` with a perfect receipt in `body.md` resolves to the literal string `$(cat body.md)` → **denied**. The inline-heredoc variant passes only by accident. Both outcomes are the parser reporting on shell source rather than on the body. Fix: part (b) — `pr-creator.md` Step 7 mandates `--body-file`; optionally the hook denies a `--body` value that starts with `$(` or `` ` `` *with a message naming `--body-file`*, rather than the receipt message.

4. **Nobody unambiguously owns copying the receipt into the PR body.** Three quotes:
   - `we/references/integration-pipeline.md:81-83` — the sole assignment, in a parenthetical: > (the receipt lives with the plan; `pr-creator` copies it into the PR body)
   - `we/agents/pr-creator.md:69-71` — the file `pr-creator` actually loads names no source: > a body carrying: **Summary**, **Changes** (from the commits), **Test Plan**, the `## Verification` block from the build's verification step. *"the build's verification step"* is not a file path; `pr-creator.md` never mentions the plan directory, the plan, or the hook.
   - `we/references/verification.md:7-9` — the contract's own consumer list omits the agent the hook fires on: > Consumers: `/we:orchestrate` (once at integration, before the PR), `/we:story` (emits the plan's verification section), `we:ac-reviewer` (checks the receipt exists and matches).
   - `we/quality/dod.md:34` — states the requirement as a *state of the PR*, with no actor: > - [ ] **The PR carries a `## Verification` block** — oracle, seed, what was asserted, what stays unproven. No block, no claim of verified.

   So: **four files name the artifact, exactly one names an owner, and that one is a parenthetical inside a file `pr-creator` never loads.** The assignment is not unambiguous — it is split between a file that binds nobody who reads it and a file that binds `pr-creator` without telling `pr-creator`. **This is the root cause of Scenario C.** Fix: one clause in `pr-creator.md:69-71` — *"the `## Verification` block copied verbatim from `docs/plans/$TICKET-story.md` § Verification (never authored here)"* — and add `pr-creator` to `verification.md:7-9`.

5. **The docstring's central promises are now false.** `we/hooks/verification_gate.py:9`:
   > Only fires on `gh pr create` (and `gh pr edit --body*`), nothing else.

   and `:11-12`:
   > Blocks on ABSENCE… Anything it cannot parse it lets through: a hook that guesses wrong is worse than no hook.

   It fired on `cat > world.md`, and it guessed wrong. Fix: these lines become true again once defect 2 is fixed — fix the code, keep the lines.

6. **The prefilter is a no-op guard presented as narrowing.** `we/hooks/verification_gate.py:121-122`:
   > if "gh" not in command or "pr" not in command:` / `    return False

   Substring, not token — matched by "through", "proven", "print", "approach". It filters nothing prose-shaped and creates the impression the hook is already narrow. Fix: delete it once the position check lands (the token scan is the real filter), or make it `re.search(r"\bgh\b", command)`.

## Cuttable lines (no-ops for an Opus-class model)

1. `we/hooks/verification_gate.py:34-47` — the whole `_HINT` template. It restates `we/references/verification.md:39-46` and `we/quality/dod.md:34`, and lines 43-44 (> ``` `not-applicable` is a legitimate answer — it just has to be said, with its reason. What is not allowed is silence.```) are a third copy of `verification.md:56-58`. **13 lines out**, replaced by the one-line pointer in Defect 1 — and the cut *strengthens* the gate rather than softening it.
2. `we/agents/pr-creator.md:101-103` — the `## Rules` block restates Steps 2, 3, 4, 8, 9 verbatim:
   > - Verify all 4 checkpoints before creating the PR; stop if any is missing.` / `- Rebase before pushing; save the `pr_created` checkpoint after success.` / `- Transition the ticket → "In Review" in Step 8 — soft-fail loud only when the workflow rejects it.
   Three lines out; the steps already say it, in order, at the point of use.
3. `we/agents/pr-creator.md:39` — > `**If ANY checkpoint missing → STOP. Tell the user which gates to run first.**` — same sentence as line 101. One of the two goes.
4. `we/agents/pr-creator.md:82` — > `See "Ticketing Integration" section below for tool detection.` — a pointer to the next heading in the same file.
5. `we/agents/pr-creator.md:9` — > `**Purpose:** Create PRs with quality gate validation.` — restates the frontmatter `description` on line 3.
6. `we/agents/pr-creator.md:15` — > `All 4 checkpoints must exist before PR creation:` — the table header carries `Required: Yes` four times; the sentence and the column are the same fact.

Net: **21 lines and one block** removed, one clause and one line added, and Scenario C stops being possible.

## What I needed and did not find

- **A pointer from `pr-creator` to the plan.** It is the only agent that must move the receipt, and it is the only artifact in the chain that never names the file holding it.
- **A denial message that distinguishes "you forgot to copy" from "verification never happened."** They are different failures with different remedies; the hook emits one text for both, and that text implies the second.
- **Anything that makes an *unfilled* receipt fail.** `_ORACLE` cannot tell a chosen oracle from the menu of oracles. A minimal strengthening: require a line matching `^\s*\**Oracle:?\**\s*(cli|ui|substitute|not-applicable)\b` — one alternative, not the pipe-joined list — and require `Seed:` / `Asserted:` lines whose values are not `<…>` placeholders.
- **A reason for the hook's file-read to be silent.** `:105` and `:111` swallow every exception and return `(True, None)` → allowed. A typo'd `--body-file` is indistinguishable from a receipt-free PR, and neither the user nor the model is told.

## Grade

**2** — the gate correctly denied my uncopied body, but it denied it with a message that points nowhere near the plan and hands over a template that satisfies the gate unfilled, so it changes the *artifact* and not the *outcome*; add the false-positive class that blocks the ordinary heredoc write of any document mentioning `gh pr create`, and the hook currently costs more sessions than it saves.
