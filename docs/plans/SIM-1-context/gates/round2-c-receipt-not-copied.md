---
type: simulation-report
chunk: gates
scenario: C — receipt in the plan, not in the PR body
round: 2
grade: 4
---
# Round 2 · Scenario C

Method: cold re-run of the scenario against the revised files, then 41 synthetic-stdin runs of
`we/hooks/verification_gate.py` against an armed throwaway repo (`.weside/config.json` →
`verification.required: true`), plus `python3 -m pytest we/hooks/test_verification_gate.py`
(**26 passed**). Nothing was executed except the hook and its test file.

## Verdict on round 1

| # | Round-1 finding | Verdict | Evidence (quoted revised line + file:line) |
|---|---|---|---|
| D1 | The gate's own remedy text satisfies the gate (`_HINT` menu line scored `_ORACLE`) | **FIXED** | `_HINT` is gone. `verification_gate.py:45` — `r"^[ \t]*\**\s*oracle\**\s*:\s*\**\s*(cli\|ui\|substitute\|not[-\s]applicable)\b[^\|\n]*$"` — the trailing `[^\|\n]*$` is what rejects the menu; `:52` `_field` — `(?![\s*]*<)` — rejects `<placeholder>` values. Pinned twice: `test_verification_gate.py:141` `test_the_unfilled_template_does_not_pass` and `:147` `test_a_chosen_oracle_over_placeholders_does_not_pass`. Re-verified live: the round-1 template denies with *"…an unfilled receipt — the seed and the assertion are still the template's placeholders"* (`:196`). |
| D2 | `_body_of` scans the whole command string, heredoc bodies included | **PARTIALLY** | Two additive constraints landed: `:70-77` `_strip_heredocs` and `:122` `if tok != "gh" or (i and argv[i - 1] not in _SEPARATORS): continue`. All 20 realistic doc-write shapes I built now pass (table below). **Not closed:** `:35` `_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)^\t*\2[ \t]*$", …)` — the tag is `\w+`, so a delimiter carrying `-` or `.` (`<<'DOC-END'`, `<<'PY-BODY'`, `<<'EOF.MD'`) is not stripped at all, and a doc line whose example follows a separator is denied. See New-1. |
| D3 | `--body` takes the token verbatim, so a command substitution is never the real body | **FIXED for the reported shape / new gap** | `:154-157` — `elif "$(" in value or "\`" in value:` … `body = heredocs[0] if len(heredocs) == 1 else None`, and `pr-creator.md:64-65` — *"Write the body to a file and pass it as `--body-file` — a body behind `--body \"$(…)\"` cannot be read by the repo's verification gate"*. Both halves of round-1's "ship (a) and (b) together" shipped. The new gap is the opposite sign — see New-2. |
| D4 | Nobody unambiguously owns copying the receipt into the PR body (**root cause of Scenario C**) | **FIXED** | `pr-creator.md:66-68` — *"the `## Verification` block **copied verbatim from `docs/plans/${TICKET}-story.md` § Verification**"* — and `:70-72` — *"**Never author that block here.** You did not run the verification, so you cannot testify to it. No block in the plan → the verification step did not happen: stop, report that, and let the Lead run it."* The path and the verb are both in the file `pr-creator` actually loads. |
| D5 | The docstring's central promises are false | **PARTIALLY** | `:9-11` — *"Fires only on a `gh pr create` / `gh pr edit` in **command position**, after heredoc bodies have been lifted out."* — is now true for the observed class. Two other promises are false: `:17-18` — *"A PR opened through an MCP tool or `gh pr create --web` never reaches this code"* — verified false, `gh pr create --web` is **denied** with *"opened with no body at all"*; and `:13-15` — *"A body it cannot resolve … it lets through"* — false for `--body "$BODY"`, which resolves to the literal string `$BODY` and is denied. See New-3. |
| D6 | The prefilter is a no-op guard presented as narrowing | **STILL OPEN** | `:169` — `if "gh" not in command or "pr" not in command:` — unchanged, still substring, still matched by "through" / "proven". Now harmless (the position check at `:122` is the real filter) but still the first thing a reader takes for the hook's narrowness. |
| Cut-1 | `_HINT` template, 13 lines, restating `verification.md:39-46` | **FIXED** | Replaced by `_WHERE` (`:58-67`), 10 lines, which says something the contract does not: *where the block already is* and *that it is not authored here*. |
| Cut-2 | `pr-creator.md:101-103` `## Rules` restating Steps 2/3/4/8/9 | **FIXED** | `## Rules` is now `:100-105`, two bullets, neither a restatement of a step. |
| Cut-3 | `pr-creator.md:39` duplicate STOP sentence | **FIXED** | Only one survives, `:34` — *"**If ANY checkpoint is missing → STOP. Tell the user which gates to run first.**"* |
| Cut-4 | `pr-creator.md:82` *"See 'Ticketing Integration' section below"* | **FIXED** | `:85-87` now points at a real file — `` `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md` ``. |
| Cut-5 | `pr-creator.md:9` `**Purpose:**` restating the frontmatter | **FIXED** | `:9` is now `---`. |
| Cut-6 | `pr-creator.md:15` *"All 4 checkpoints must exist"* over a `Required: Yes` column | **FIXED** | The table starts at `:13`; the sentence is gone. |
| Need-1 | A pointer from `pr-creator` to the plan | **FIXED** | `pr-creator.md:66-68`, quoted at D4. |
| Need-2 | A message distinguishing "you forgot to copy" from "verification never happened" | **FIXED** | Three distinct denials (`:189` no body, `:192` no receipt, `:196` unfilled receipt) over one `_WHERE`, whose second paragraph (`:64-65`) is the distinction: *"If the plan carries no such block, verification did not happen. Say so and stop; do not write a receipt for a run that did not take place."* |
| Need-3 | Anything that makes an *unfilled* receipt fail | **FIXED** | `:44-47` + `:50-52` + `:195`, quoted at D1. |
| Need-4 | A reason for the hook's file-read to be silent | **ACCEPTED, not fixed** | `:151-153` still swallows every exception, and `test_verification_gate.py:100-102` now pins that as intent. Cost is low in practice: `gh` itself fails on a missing `--body-file`, so no PR opens. Not carried forward as a defect. |
| — | `verification.md:7-9` consumer list omits `pr-creator` | **FORK** | Still — *"Consumers: `/we:orchestrate` …, `/we:story` …, `we:ac-reviewer` …"*. `verification.md` is out of scope for this revision. Now cosmetic, because `pr-creator.md` binds `pr-creator` directly. |
| — | `dod.md:34` states the requirement with no actor | **FIXED elsewhere** | `dod.md:34` is byte-identical — *"**The PR carries a `## Verification` block** … No block, no claim of verified."* — but it is a DoD row, and a DoD row is a state, not an assignment. The actor now lives where it belongs, in `pr-creator.md:66-68`. |

## Trace on the revised files

I am `we:pr-creator`, dispatched `Create PR for TICKET-101`, entering at Step 6.

1. **Step 6 — `gh` availability.** `Bash: gh auth status`. `_refusal:169` — `"pr" not in command` → return None. Allowed. Authenticated, so Steps 7–8 run.

2. **Step 7, before any tool call.** `pr-creator.md:62-68` is read as one sentence with two obligations, and both bind before I compose anything:
   - *"Write the body to a file and pass it as `--body-file`"* — so the round-1 attempt-1 shape (`--body "$(cat <<'EOF' … )"`) is never built. The clause gives its reason in-line, which is what makes it stick: *"a body behind `--body \"$(…)\"` cannot be read by the repo's verification gate, which then either blocks a good PR or waves a bad one through."*
   - *"the `## Verification` block **copied verbatim from `docs/plans/${TICKET}-story.md` § Verification**"* — a path, not a phase name. Round 1 had *"from the build's verification step"*, which is not a file.

   So I `Read docs/plans/TICKET-101-story.md` **before** assembling the body, find the complete block (oracle `cli`, seed `weside widgets create --json`, asserted `201 + id`, not proven: push + device geometry) and paste it. `:70-71` — *"**Never author that block here.** You did not run the verification, so you cannot testify to it."* — removes the alternative even if the plan had been empty.

3. **The write.** `Bash: cat > pr-body-TICKET-101.md <<'EOF' … EOF`. Hook: prefilter passes on prose substrings, `_strip_heredocs:70-77` lifts the body out, no `gh` survives in command position → `(None, None, False)` at `:129` → allowed.

4. **Step 7, the call.** `Bash: gh pr create --title "TICKET-101: Widgets" --body-file pr-body-TICKET-101.md`. Hook: `--body-file` branch `:140-141`, file read at `:150`, `_HEADING` + `_ORACLE` + `_SEED` + `_ASSERTED` all match → `:198` returns None. Allowed. PR opens.

**Answer to (1): one attempt, zero denials.** The revised Step 7 does make me open the plan and copy the block, and it does so *before* the first tool call — Scenario C is closed at the source, not gated. That is the right place for it: a gate that has to fire is a gate that already cost a cycle.

**Counterfactual, so the gate is judged too.** Had I ignored Step 7 and built the body from the ticket summary and `git log --oneline` alone, `gh pr create --body-file pr-body.md` is denied at `:192`, and the denial reads (verified live):

> This PR claims work is done without saying how that was observed. Unit tests do not count — they share the blind spots of whoever wrote the code.
>
> The receipt is not authored here: copy the `## Verification` block verbatim from the story plan (`docs/plans/<TICKET>-story.md` § Verification) into the PR body, and pass the body as `--body-file` so it can be read. …

Round 1's central complaint — *"it never names `docs/plans/TICKET-101-story.md`, never says the receipt already exists, never says copy"* — is answered in the first clause of the remedy, and the cheapest path out of the denial is now the correct one instead of echoing the message back.

5. **Steps 8–9.** Jira comment + transition (soft-fail), then `python3 …/orchestration.py story checkpoint TICKET-101 pr_created` — `"pr"` is in `pr_created`, `"gh"` is not in the command → `:169` returns None. Allowed.

## False-positive hunt

41 commands run through the hook with synthetic stdin against an armed repo. The realistic
doc-writing class — round 1's live regression — is **closed: 20 of 20 allowed.**

| Command tried | Hook's answer | Correct answer | Verdict |
|---|---|---|---|
| `cat > notes.md <<'WEOF'` … doc with a fenced `gh pr create --title 'T' --body 'x'` … `WEOF` (round 1's live regression) | allow | allow | ✅ fixed |
| same, unquoted delimiter `<<WEOF` | allow | allow | ✅ |
| `tee notes.md <<'EOF'` … same doc … `EOF` | allow | allow | ✅ |
| `python3 - <<'PY'` … `print('run: gh pr create --body-file b.md')` … `PY` | allow | allow | ✅ |
| heredoc doc that itself shows a heredoc (an inner `EOF` line) then `gh pr create … --body-file b.md` | allow | allow | ✅ nested terminator does not re-expose the tail |
| two heredoc doc writes in one command, both quoting the command | allow | allow | ✅ |
| `( cd … && cat > notes.md <<'EOF' … EOF )` | allow | allow | ✅ |
| `git commit -F - <<'EOF'` … body quoting `gh pr create --title T --body-file b.md` … `EOF` | allow | allow | ✅ |
| `git commit -m 'docs: explain gh pr create --body-file'` | allow | allow | ✅ quoted → one token |
| `rg -n 'gh pr create --body' docs/` | allow | allow | ✅ |
| `grep -rn -e gh -e pr -e create --include=*.md .` | allow | allow | ✅ |
| `ls *.md \| xargs -I{} grep -l 'gh pr create --body' {}` | allow | allow | ✅ |
| `printf 'gh pr create --body x' \| tee notes.md` | allow | allow | ✅ |
| `echo gh pr create --body x >> notes.md` | allow | allow | ✅ `echo` is not a separator |
| `# gh pr create --body-file b.md` | allow | allow | ✅ |
| `sed -i "s/gh pr create --body/gh pr create --body-file/" docs/x.md` | allow | allow | ✅ |
| `curl -X POST --body 'gh pr create --body x' …` | allow | allow | ✅ |
| `gh pr view 42 --json body`, `gh pr checks 42` | allow | allow | ✅ |
| `gh pr edit 42 --add-label ready` | allow | allow | ✅ no body flag, not a new claim |
| `gh pr create --body "unbalanced` (unbalanced quotes) | allow | allow | ✅ `:117` |
| **`cat > n.md <<'DOC-END'` … `Run this:  git push && gh pr create --title T --body x` … `DOC-END`** | **deny** | allow | ❌ **New-1** — tag `DOC-END` is not `\w+`, heredoc not stripped |
| **`cat > n.md <<'EOF.MD'` … `true \| gh pr create --body x` … `EOF.MD`** | **deny** | allow | ❌ New-1 |
| **`cat > n.md <<'Q.Q'` … `then gh pr create --body x` … `Q.Q`** | **deny** | allow | ❌ New-1 |
| `cat > n.md <<'EOF'` … `EOF` terminator indented with **spaces** | deny | — | ⚪ control arm: not valid bash (`<<-` strips tabs only, and `^\t*\2` matches bash exactly). Not a finding. |
| `cat > n.md <<'EOF'` … heredoc never terminated | deny | — | ⚪ control arm: not a valid command. Not a finding. |
| `cd . && printf '%s' && gh pr create --body x` | deny | deny | ⚪ control arm: this really is a `gh pr create`. Correct. |
| `gh pr create --body-file no-receipt.md` | deny | deny | ✅ |
| `git push && gh pr create --body-file no-receipt.md` | deny | deny | ✅ pinned at `test:189` |
| `git push ; gh pr create --body-file no-receipt.md` | deny | deny | ✅ |
| `gh pr create \` newline `  --body-file no-receipt.md` (backslash continuation) | deny | deny | ✅ |
| `gh pr create --body-file=no-receipt.md` / `--body='shipped it'` | deny | deny | ✅ `=` forms |
| `gh pr create --fill` / `--title` only / `--draft --fill-verbose` | deny | deny | ✅ |
| `gh pr edit 42 --body-file no-receipt.md` | deny | deny | ✅ |
| `gh pr create -F no-receipt.md` / `-b 'just shipping it'` | deny | deny | ✅ short flags |
| `gh pr create --body-file receipt.md` / receipt inside `--body "$(cat <<'EOF' … EOF)"` / `--body '<inline receipt>'` | allow | allow | ✅ |
| `gh pr create --body-file no-receipt.md --body-file receipt.md` | allow | allow | ✅ last-wins matches `gh` |
| **`git push -u origin b` ⏎ `gh pr create --body-file no-receipt.md`** | **allow** | deny | ❌ **New-4** — newline is not in `_SEPARATORS` |
| **`cat > b.md <<'EOF' … EOF` ⏎ `gh pr create --body-file no-receipt.md`** | **allow** | deny | ❌ **New-4**, and this is the shape Step 7 steers into |
| **`gh pr create --body 'shipped \`foo\`'`** | **allow** | deny | ❌ **New-2** — one backtick disarms the whole `--body` path |
| **`gh pr create --body "$BODY"`** | **deny** | allow | ❌ **New-3** — unresolvable, but fail-closed |
| `GH_TOKEN=x gh pr create --body-file no-receipt.md` | allow | deny | ❌ New-4b, env prefix |
| `/usr/bin/gh pr create --body-file no-receipt.md` | allow | deny | ❌ New-4b, path-qualified binary |
| `bash -c 'gh pr create --body-file no-receipt.md'`, `printf x \| xargs -I{} gh pr create …` | allow | deny | ⚪ contrived; unreachable by the position check by construction |
| `gh pr create --web` | deny | (see New-3) | ❌ contradicts `:17-18` |

**Answer to (2): the class round 1 reported is closed; a narrowed remnant survives.** The two
constraints that landed are additive, exactly as round 1 predicted, and I could not make any
*realistic* documentation write deny — except by naming the heredoc delimiter with a hyphen or a
dot. `<<'PY-BODY'`, `<<'EOF.MD'`, `<<'END-OF-DOC'` are ordinary spellings, and a runbook line
`git push && gh pr create …` is the single most likely sentence in a document about opening PRs.

## Still open / new

1. **New-4 — a newline is not a command separator, and Step 7 steers into exactly that shape.** IN-SCOPE (`hooks/verification_gate.py`, `hooks/test_verification_gate.py`).
   `verification_gate.py:38`:
   > `_SEPARATORS = frozenset({"&&", "||", ";", "|", "&", "(", ")", "{", "}", "then", "do", "else", "!"})`

   `shlex.split` discards newlines as ordinary whitespace, so in a multi-line Bash call the token before `gh` is the last word of the previous line and `:122` skips it. Verified: `git push -u origin b` ⏎ `gh pr create --body-file no-receipt.md` → `_body_of` returns `(None, None, False)` → **allowed**.
   This is not one item in a list. `pr-creator.md:64` now says *"Write the body to a file and pass it as `--body-file`"*, and the economical implementation of that sentence is **one** Bash call — `cat > pr-body.md <<'EOF' … EOF` ⏎ `gh pr create … --body-file pr-body.md` — which is the second row above and is allowed. The gate's coverage now depends on whether the agent emits one Bash call or two, and nothing anywhere pins that. Note `test_verification_gate.py:189` `test_after_a_separator_gh_still_counts` uses `&&`: the author thought about separators and pinned the one that works, so 26/26 green is not evidence the separator logic is complete.
   **Smallest fix:** one line in `_body_of`, after `:113`, before the split — `stripped = re.sub(r"[\n\r]+", " ; ", stripped)`. Heredoc bodies are already lifted out at that point, so no document newline reaches it. Verified in both directions: the two rows above now deny; the doc-write heredoc still allows; the inline-heredoc receipt still resolves; a newline inside a quoted `-m` string and a backslash continuation produce no new match, because the inserted `;` lands inside the quoted token. **Test that would have caught it:** `test_a_newline_separates_commands(armed)` asserting `refuse(f"git push\ngh pr create --body-file {name}", armed) is not None`.

2. **New-2 — one backtick disarms the entire `--body` path, so the only guarded transport is the one `pr-creator.md` already mandates.** IN-SCOPE (`hooks/verification_gate.py`).
   `verification_gate.py:154-157`:
   > `elif "$(" in value or "\`" in value:` / `    # An unexpanded substitution — PreToolUse runs before the shell. …` / `    body = heredocs[0] if len(heredocs) == 1 else None`

   A backtick is not only command substitution — it is the markdown code span, and a PR body almost always contains one. Verified: `gh pr create --body 'shipped \`foo\`'`, no receipt, no heredoc → `body = None` → `:182` `elif body is None: return None` → **allowed**. Together with the `$(` half, an inline `--body` is effectively unguarded, not merely gapped. The consequence worth stating plainly: **the hook's coverage is conditional on the compliance the hook exists to enforce** — `--body-file` is guarded, and `--body-file` is exactly what `pr-creator.md:64` tells a cooperative agent to use. The agent that ignores Step 7 is the agent the gate does not catch.
   **Smallest fix:** narrow the unresolvable test to a real substitution — `re.search(r"\$\(|\`[^\`]*\`", value)` is still wrong for code spans; better is `"$(" in value or value.count("\`") % 2 == 1 or "\`$" in value`, or simply drop the backtick clause and keep `$(`, accepting that a genuine backtick-substitution body reads as literal. **Test:** `test_a_code_span_in_the_body_does_not_disarm_the_gate` — `--body 'shipped \`foo\`, no receipt'` must deny.

3. **New-3 — the resolution branches disagree on which way to fail, and the docstring states the wrong one twice.** IN-SCOPE (`hooks/verification_gate.py`).
   `verification_gate.py:13-15`:
   > `  * A body it cannot resolve (a command substitution with no heredoc behind it, an unreadable \`--body-file\`) it lets through: a hook that guesses wrong is worse than no hook.`

   Verified false for a plain variable: `gh pr create --body "$BODY"` falls to `:159` `body = value`, resolves to the literal five characters `$BODY`, fails `_HEADING` and is **denied** — an agent whose receipt is correctly in the variable is blocked with a message telling it to copy a block it already copied. `$(` and backtick fail open, `$VAR` fails closed, and nothing in the code says why.
   Same docstring, `:17-18`:
   > `  * One transport. A PR opened through an MCP tool or \`gh pr create --web\` never reaches this code; the gate is armed against one spelling of the action.`

   Verified false for the second half: `gh pr create --web` → `('create', None, False)`, `seen` is False and `verb == "create"`, so `:179-180` falls through and `:189` denies with *"opened with no body at all"*. Whether denying `--web` is right is arguable — it opens a browser form a human fills — but a docstring promising it is out of scope while the code blocks it is the class round 1 already flagged as D5.
   **Smallest fix:** add `"$" in value` to the unresolvable branch at `:154` so all three unexpanded shapes fail the same way, and delete `--web` from `:17-18` (or exempt it at `:179` — `--web` is a human handing over, not a claim).
   **Test:** `test_an_unexpanded_variable_body_lets_through`.

4. **New-1 — the heredoc tag is `\w+`, so a hyphenated or dotted delimiter leaves the document in argv.** IN-SCOPE (`hooks/verification_gate.py`, `hooks/test_verification_gate.py`).
   `verification_gate.py:35`:
   > `_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)^\t*\2[ \t]*$", re.MULTILINE | re.DOTALL)`

   `DOC-END`, `PY-BODY`, `EOF.MD`, `END-OF-DOC` are not `\w+`, so the regex does not match at all and **nothing is stripped**; the document then reaches `shlex` whole, and any example line following a separator token (`&&`, `|`, `then`) satisfies `:122`. Verified: `cat > n.md <<'DOC-END'` over the line `Run this: git push && gh pr create --title T --body x` → **denied**, with the receipt message, on a command that opens no PR. This is round 1's exact regression, surviving in a narrower spelling — and it fires on documents about PR workflow, which is the document class this plugin writes most.
   **Smallest fix:** `(\w+)` → `([^\s'\"]+)` at `:35`. Verified: the same command then strips to `cd /d && cat > n.md <<HEREDOC` → allowed. The backreference `\2` matches literally, so a `.` in the tag is safe, and every delimiter in the existing suite (`EOF`, `WEOF`, `PY`) still matches. **Test:** `test_a_hyphenated_heredoc_delimiter_is_still_a_heredoc`.

5. **New-5 — the hook's remedy is a retry instruction and `pr-creator.md` forbids the retry.** IN-SCOPE (`pr-creator.md`).
   `pr-creator.md:72-73`:
   > `The same holds if the PR call is refused by a hook — report the refusal message verbatim and stop.`

   against `verification_gate.py:59-61`:
   > `"The receipt is not authored here: copy the \`## Verification\` block verbatim from the story plan (\`docs/plans/<TICKET>-story.md\` § Verification) into the PR body, and pass the body as \`--body-file\` so it can be read."`

   The denial hands over a mechanical remedy — copy this block, switch this flag — and Step 7 forbids acting on it. A refusal caused by the *wrong flag* or the *wrong file path*, where the plan's block exists and I simply did not paste it, ends the dispatch and costs a Lead round-trip for an edit I could make in one tool call. The stop-rule is right in its motivating case (it is what closes round 1's fabrication loop) and wrong in the mechanical one; it does not currently distinguish them. Rank below New-4: the cost is one wasted cycle, not a wrong artifact.
   **Smallest fix:** replace `:73` with — *"The same holds if the PR call is refused because the plan has no block. A refusal naming a mechanical fix that authors nothing — a wrong flag, an unreadable body file — may be fixed once and retried once; a second refusal is a stop."*

6. **D6 carried forward — the prefilter still advertises a narrowness it does not provide.** IN-SCOPE (`hooks/verification_gate.py`).
   `verification_gate.py:169`:
   > `if "gh" not in command or "pr" not in command:`

   Substring, not token: "through", "proven", "approach", "print" all pass it. Harmless since `:122` landed, but it is the first filter a reader meets and it reads as the gate's narrowing when the real narrowing is 47 lines away. **Smallest fix:** delete it (the token scan is the filter), or `re.search(r"\bgh\b", command)`.

7. **FORK — `verification.md:7-9` still omits the agent the hook fires on.**
   > `Consumers: \`/we:orchestrate\` (once at integration, before the PR), \`/we:story\` (emits the plan's verification section), \`we:ac-reviewer\` (checks the receipt exists and matches).`

   `pr-creator` moves the receipt and is the only agent the gate denies, and the contract's own consumer list does not name it. Cosmetic now that `pr-creator.md:66-68` binds directly; `verification.md` was not in this revision's scope.

## Grade

**4** — the two round-1 defects that mattered are genuinely closed and pinned by tests: the gate no
longer accepts its own hint (`:44-47`, `:50-52`, pinned at `test:141` and `test:147`), and the
receipt now has a named owner with a file path in the file that agent loads (`pr-creator.md:66-68`),
so Scenario C is prevented rather than caught — one attempt, zero denials, and the counterfactual
denial does point at the plan. The reported false-positive class is closed across all 20 realistic
doc-write shapes I could build. Against that: `pr-creator.md:64` steers toward a one-call
`cat` + `gh` shape that `_SEPARATORS` cannot see, so the fix and the gap were introduced together
and no test covers the seam; a hyphenated heredoc delimiter still denies a document; and two
docstring promises (`:13-15`, `:17-18`) are verifiably false in the same way round 1's were. Not a
5 while a compliant agent's most natural single command walks straight through the gate.
