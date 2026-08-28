---
type: simulation-report
chunk: gates
scenario: C — receipt in the plan, not in the PR body
round: 3
grade: 4
---
# Round 3 · Scenario C

Method: cold re-run of the scenario against the revised files, then 63 synthetic-stdin runs of
`we/hooks/verification_gate.py` against an armed throwaway repo (`.weside/config.json` →
`verification.required: true`), plus `python3 -m pytest we/hooks/test_verification_gate.py`
(**42 passed**). Nothing was executed except the hook and its test file.

## Verdict on round 2

| # | Round-2 finding | Verdict | Evidence (quoted current line + file:line) |
|---|---|---|---|
| New-1 | Heredoc tag is `\w+`, so `<<'DOC-END'` / `<<'EOF.MD'` leaves the document in argv | **FIXED** | `verification_gate.py:37` — `r"<<-?[ \t]*(['\"]?)([^\s'\"]+)\1[^\n]*\n(.*?)^\t*\2[ \t]*$"`. Verified live: `DOC-END`, `EOF.MD`, `Q.Q`, `EOF_1`, `END/DOC`, `PY-BODY`, `<< 'EOF'` with a space — all seven allowed. Pinned at `test_verification_gate.py:339` `test_a_hyphenated_heredoc_delimiter_is_still_a_heredoc` and `:353` `test_a_python_heredoc_is_not_a_pr`. |
| New-2 | One backtick disarms the whole `--body` path (a markdown code span reads as a substitution) | **FIXED** | `:207` — `elif "$" in value or value.count("`") % 2:` — an *odd* count is unresolvable, a balanced pair stays readable. Verified: `gh pr create --body 'shipped `foo`, no receipt'` → **denied**; `--body '## Verification … **Seed:** `weside widgets create --json` …'` → allowed. Pinned at `test:344`. |
| New-3 | Resolution branches disagree on which way to fail; the docstring states the wrong one twice | **FIXED (both halves)** | `$VAR` now joins the unresolvable branch at the same `:207` (`"$" in value`) — `gh pr create --body "$BODY"` → allowed, pinned at `test:348`. `--web` is exempted in code at `:188` — `if "--web" in rest: return (verb, None, True)` — and the docstring now matches it: `:17-19` — *"A PR opened through an MCP tool never reaches this code, and `--web` types its body in a browser we cannot read"*. Pinned at `test:295`. |
| New-4 | A newline is not a command separator, and Step 7 steers into exactly that shape | **PARTIALLY — the separator half landed, the shape it steers into is now *mis*-resolved** | The rewrite shipped: `:45` — `_NEWLINE = re.compile(r"\n(?=(?:[^'\"]|'[^']*'|\"[^\"]*\")*$)")` — and `:176` — `stripped = _NEWLINE.sub(" ; ", stripped)`. `git push -u origin b` ⏎ `gh pr create --body-file <no receipt>` now **denies** (pinned at `test:263`). But the one-Bash-call shape `pr-creator.md:62` mandates — heredoc-write the body file, then `gh pr create --body-file` — is now *seen* and resolved against the file **as it exists before the command runs**. See New-6; this is the same seam, with a new failure mode. |
| New-5 | The hook's remedy is a retry instruction and `pr-creator.md` forbids the retry | **FIXED** | `pr-creator.md:70-72` — *"The same holds if the PR call is refused by a hook for a missing block. A refusal naming a mechanical fix that authors nothing — a wrong flag, an unreadable body file — you fix once and retry once; a second refusal is a stop, with its message reported verbatim."* The two cases round 2 asked to be distinguished are distinguished, and the budget is named. |
| D6 | The prefilter is a no-op guard presented as narrowing | **STILL OPEN** | `:250` — `if "gh" not in command or "pr" not in command:` — byte-identical to round 2. Substring, not token: "through", "proven", "approach", "print" all pass it. Harmless (the real filter is `_pr_verb`/`_starts_a_command` at `:158-165`), but still the first thing a reader takes for the hook's narrowness. |
| Need-4 | The hook's file read swallows every exception | **ACCEPTED in round 2, now load-bearing in the wrong direction** | `:202-206` — `try: … except Exception: body = None`. Round 2 priced this at "`gh` itself fails on a missing `--body-file`, so no PR opens". That is no longer the whole cost: since `:176` made the one-call shape visible, the same silent `body = None` is what lets an unwritten body file through. Folded into New-6. |
| FORK | `verification.md:7-9` consumer list omits `pr-creator` | **STILL OPEN — FORK** | `verification.md:7-9` — *"Consumers: `/we:orchestrate` (once at integration, before the PR), `/we:story` (emits the plan's verification section), `we:ac-reviewer` (checks the receipt exists and matches)."* Cosmetic: `integration-pipeline.md:81-82` already says *"the receipt lives with the plan; `pr-creator` copies it into the PR body"*, and `pr-creator.md:65-66` binds the agent directly. `verification.md` was again not in this revision's scope. |
| — | `dod.md:34` states the requirement with no actor | **unchanged, correctly** | `dod.md:34` is byte-identical. A DoD row is a state, not an assignment; the actor lives in `pr-creator.md:65-66` and `integration-pipeline.md:81-82`. |

## Trace

I am `we:pr-creator`, dispatched `Create PR for TICKET-101`, entering at Step 6.

1. **Step 6 — `gh` availability.** `Bash: gh auth status`. `:250` — `"pr" not in command` → return None. Allowed. Authenticated, so Steps 7–8 run.

2. **Step 7, before any tool call.** `pr-creator.md:62-66` binds twice before I compose anything: *"Write the body to a file and pass it as `--body-file`"*, and *"the `## Verification` block **copied verbatim from `docs/plans/${TICKET}-story.md` § Verification**"* — a path, not a phase name. So I `Read docs/plans/TICKET-101-story.md` **first**, find the complete block (oracle `cli`, seed `weside widgets create --json`, asserted `201 + id`, not proven: push + device geometry) and paste it. `:68` — *"**Never author that block here.**"* — removes the alternative had the plan been empty.

3. **The write.** `Bash: cat > pr-body-TICKET-101.md <<'EOF' … EOF`. Heredoc stripped at `:108-115`, no `gh` in command position → `(None, None, False)` → allowed.

4. **Step 7, the call.** `Bash: gh pr create --title "TICKET-101: Widgets" --body-file pr-body-TICKET-101.md`. `--body-file` branch `:151-152`, file read at `:203`, `_HEADING` + `_oracles` + `_filled("seed")` + `_filled("asserted")` all pass → `:271` returns None. Allowed. PR opens.

**Answer to (1): one attempt, zero denials.** Unchanged from round 2, and still for the right reason — Scenario C is closed at the source by Step 7, not by the gate.

**But note *how* it is closed, because round 3's finding lives here.** Had I written the body and opened the PR in **one** Bash call — `cat > pr-body.md <<'EOF' … EOF` ⏎ `gh pr create --body-file pr-body.md`, which is the most economical reading of `pr-creator.md:62` — the hook now finds `gh` in command position (the `:176` rewrite) but reads `pr-body.md` **before the heredoc has written it**. Verified live, four ways, against an armed repo:

| One-call shape | On-disk state of the body file | Hook | Correct |
|---|---|---|---|
| heredoc writes a **good** receipt | file does not exist yet | allow | allow (by accident — unresolvable) |
| heredoc writes **no** receipt | file does not exist yet | **allow** | deny |
| heredoc writes **no** receipt | stale file *has* a receipt | **allow** | deny |
| heredoc writes a **good** receipt | stale file has *no* receipt | **deny** | allow |

The last row is the harm story, and it is reachable by the ordinary retry path that
`pr-creator.md:70-72` now authorises:

1. Attempt 1, two calls: body file written without the receipt, `gh pr create --body-file pr-body.md` → **denied**, correctly, with the remedy naming `docs/plans/<TICKET>-story.md`.
2. I copy the block. The cheapest fix is one call: rewrite the file and re-run `gh`. → **denied again**, on a body that now carries the receipt, because the hook read the file's pre-write bytes.
3. `pr-creator.md:71-72` — *"you fix once and retry once; a second refusal is a stop"* — so I stop and report. A correct PR does not open.

## False-positive hunt

63 commands run against an armed repo. **46 of 46 commands that open no PR were allowed — zero
false positives.** The class round 1 reported and round 2 narrowed to a hyphenated delimiter is
closed across every delimiter spelling I could construct.

| Command tried | Hook | Correct | Verdict |
|---|---|---|---|
| `cat > notes.md <<'WEOF'` / `<<WEOF` / `<<"WEOF"` / `<<-EOF` (tab terminator) — doc quoting `gh pr create` | allow | allow | ✅ |
| `<<'DOC-END'`, `<<'EOF.MD'`, `<<'Q.Q'`, `<<'EOF_1'`, `<<'END/DOC'`, `<< 'EOF'` (space) | allow | allow | ✅ **New-1 closed** — every one denied in round 2 |
| `python3 - <<'PY-BODY'` / `python3 - <<PY` printing the command | allow | allow | ✅ |
| `tee notes.md <<'EOF'` / `tee -a notes.md <<'EOF'` | allow | allow | ✅ |
| `git commit -F - <<'EOF'` whose message quotes `git push && gh pr create --body-file b.md` | allow | allow | ✅ |
| heredoc doc that itself shows a heredoc (inner `EOF` line inside an `OUTER` delimiter) | allow | allow | ✅ |
| two heredoc doc writes in one command | allow | allow | ✅ |
| `( cd . && cat > n.md <<'EOF' … EOF )` and `{ cat > n.md <<'EOF' … EOF ; }` | allow | allow | ✅ |
| **heredoc doc whose text is a newline-separated example** (`git push` ⏎ `gh pr create --body-file b.md`) | allow | allow | ✅ the `:176` rewrite runs *after* `_strip_heredocs`, so no document newline reaches it |
| `tee n.md <<'DOC-1'` with the same newline-separated example | allow | allow | ✅ |
| `echo "step 1: git push\nstep 2: gh pr create --body x" > notes.md` (real newline inside quotes) | allow | allow | ✅ the `:45` lookahead holds |
| `git commit -m "docs: runbook⏎⏎see: gh pr create --body-file b.md"` (real newlines inside `-m`) | allow | allow | ✅ |
| `awk '⏎/gh pr create/ {print}⏎' docs/runbook.md` (newlines inside a quoted script) | allow | allow | ✅ |
| `rg -n 'gh pr create --body' docs/` · `grep -rn -e gh -e pr -e create` · `ls *.md \| xargs -I{} grep -l …` | allow | allow | ✅ |
| `sed -i "s/gh pr create --body/gh pr create --body-file/" docs/x.md` | allow | allow | ✅ |
| `echo 'gh pr create --body x' >> notes.md` · `printf 'gh pr create --body x' \| tee notes.md` | allow | allow | ✅ |
| `git commit -m 'docs: explain gh pr create --body-file'` · `# gh pr create --body-file b.md` | allow | allow | ✅ |
| `curl -X POST --body 'gh pr create --body x' …` | allow | allow | ✅ |
| `gh pr view 42 --json body && gh pr checks 42 && gh pr list` | allow | allow | ✅ |
| `gh pr edit 42 --add-label ready` · `gh pr comment 42 --body 'no receipt'` | allow | allow | ✅ neither is a create/edit body |
| `gh pr create --web` | allow | allow | ✅ **New-3 closed** (`:188`) |
| `gh pr create --body "$BODY"` · `--body "$(cat body.md)"` · unbalanced quote · `--body-file typo.md` | allow | allow | ✅ four unresolvable shapes, one direction |
| **`--body` value that legitimately contains the words** — a receipt whose Summary reads *"Documents gh pr create --body-file usage"* | allow | allow | ✅ |
| **`--body` value containing balanced code spans** (`` `weside widgets create --json` ``) + a full receipt | allow | allow | ✅ **New-2 closed** |
| `gh pr create --body-file receipt.md` · receipt via `--body "$(cat <<'EOF' … EOF)"` · `--body-file no-receipt.md --body-file receipt.md` (last wins) | allow | allow | ✅ |
| **`cat > pr-body.md <<'EOF'` ⏎ good receipt ⏎ `EOF` ⏎ `gh pr create --body-file pr-body.md`, file stale and receiptless** | **deny** | allow | ❌ **New-6** — the file is read before the write |
| `cat > n.md <<'EOF'` ⏎ `EOF` ⏎ `git push && gh pr create --body x` ⏎ `EOF` | deny | — | ⚪ control arm: real bash also ends the heredoc at the bare `EOF` line, so the tail genuinely *is* command text. Not a finding. |
| `cat > n.md <<'EOF'` never terminated | deny | — | ⚪ control arm: not a valid command. |
| `git push && \| ; \| newline \| backslash-continuation` + `gh pr create --body-file no-receipt.md` (4 shapes) | deny | deny | ✅ **New-4's separator half closed** — the newline row denied in round 2 |
| `git push\r\ngh pr create --body-file no-receipt.md` (CRLF) | deny | deny | ✅ |
| `GH_TOKEN=x gh …` · `env GH_TOKEN=x gh …` · `command gh …` · `exec gh …` · `/usr/bin/gh …` | deny | deny | ✅ `:44` `_PREFIXES` + `:56` `"=" in prev` + `:161` `tok.endswith("/gh")` |
| `gh pr create --fill` · `--title 'T'` only | deny | deny | ✅ *"no body at all"* |
| `-b 'just shipping it'` · `--body='shipped it'` · `-F` · `--body-file=` | deny | deny | ✅ every flag spelling |
| `gh pr create --body 'shipped `foo`, no receipt'` | deny | deny | ✅ |
| `gh pr edit 42 --body-file no-receipt.md` · `cd . && gh pr create …` · `true \| gh pr create …` · `( gh pr create … )` | deny | deny | ✅ |
| **`cat > fresh.md <<'EOF'` ⏎ no receipt ⏎ `EOF` ⏎ `gh pr create --body-file fresh.md`** | **allow** | deny | ❌ **New-6**, false-negative direction |
| `if git push; then gh pr create --body-file no-receipt.md; fi` | allow | deny | ⚪ the trailing `;` glues onto the filename (`no-receipt.md;`) → unreadable → documented fail-open at `:13-16`. Contrived. |
| `timeout 60 gh …` · `bash -c 'gh …'` · `printf x \| xargs -I{} gh …` | allow | deny | ⚪ contrived; a prefix with its own argument, and two quoted-subcommand forms, are out of the position check by construction. |
| `git push` ⏎ `gh pr create --body-file no-receipt.md  # don't forget` | allow | deny | ⚪ the stray apostrophe makes `shlex.split` raise → `:179-180` fail-open, the same path `test:98` already pins. |

**Answer to (2): no command that opens no PR is denied — except one, and it is the shape Step 7
mandates.** Every wrongly-denied shape round 2 reported is gone. The single surviving false
positive and the single realistic false negative are the same defect, New-6, in its two
directions.

## Still open / new

1. **New-6 — the body file is read before the command that writes it, so the one-call shape Step 7 mandates is resolved against the wrong bytes.** IN-SCOPE (`hooks/verification_gate.py`, `hooks/test_verification_gate.py`). **NEW — introduced by this revision.**
   `verification_gate.py:176`:
   > `    stripped = _NEWLINE.sub(" ; ", stripped)`

   with `:202-206`:
   > `        if is_file:` / `            try:` / `                with open(os.path.join(cwd or "", value)) as fh:` / `                    body = fh.read()` / `            except Exception:` / `                body = None`

   A PreToolUse hook runs **before** the shell. Until `:176` landed, `cat > b.md <<'EOF' … EOF` ⏎ `gh pr create --body-file b.md` was invisible (round 2's New-4) and therefore allowed. It is now visible, and `:203` opens `b.md` as it stands *before* the heredoc writes it. Four verified outcomes, listed in the Trace table: an absent file fails open (a receiptless PR opens), and a **stale** file decides the verdict — including denying a PR whose body now carries the receipt. `pr-creator.md:70-72` grants exactly one retry, so that denial ends the dispatch.
   The information needed is already in the function: `_strip_heredocs` returns the text. Verified — for the failing case, `heredocs == ['## Summary\nno receipt\n']` while `body` came back `None`.
   **Smallest fix, two parts, the first alone worth shipping.** (a) *Stop reading stale bytes.* Before `:202`, if `value` is a redirect or `tee` target in this same command, do not open it — return unresolvable and fail open, which is exactly what `:13-16` already promises for a body it cannot resolve. That removes the false positive, the expensive direction. (b) *Optionally recover the body:* when the same command carries heredocs, resolve from `"\n".join(heredocs)` as the `--body` branch already does at `:212`. (b) closes the false negative only for the heredoc spelling — `printf > file`, `cp`, and a `Write` tool call before the Bash call are unrecoverable by construction, so the gate's coverage still depends on the transport. Say that in the docstring rather than implying otherwise.
   **Why 42 green is not evidence:** `test_verification_gate.py:263` `test_a_newline_starts_a_command` uses `body_file(armed, NO_RECEIPT)` — a file **already on disk**. It exercises the separator rewrite and never the same-call write, which is the only new behaviour the rewrite unlocked. **Test that would have caught it:** `test_a_body_file_written_in_the_same_command_is_not_read_from_disk(armed)` — write a receiptless `pr-body.md`, then assert `refuse(f"cat > pr-body.md <<'EOF'\n{RECEIPT}EOF\ngh pr create --body-file pr-body.md", armed) is None`.

2. **D6 carried forward — the prefilter still advertises a narrowness it does not provide.** IN-SCOPE (`hooks/verification_gate.py`).
   `verification_gate.py:250`:
   > `    if "gh" not in command or "pr" not in command:`

   Unchanged for two rounds. Substring, not token — "through", "proven", "approach", "print" all pass it — while the real narrowing is `_starts_a_command` at `:48-57`, 200 lines away. Harmless to behaviour; it is the first filter a reader meets and it misdescribes the gate. **Smallest fix:** delete it, or `re.search(r"\bgh\b", command)`.

3. **Docstring `:13-16` is now true, and truthfully documents the hole.** IN-SCOPE, informational.
   > `  * A body it cannot resolve (a command substitution with no heredoc behind it,` / `    an unreadable \`--body-file\`) it lets through: a hook that guesses wrong is` / `    worse than no hook.`

   Round 2's D5/New-3 complaint is answered — `$(`, backtick-odd, `$VAR`, `--web` and an unreadable file all now fail open, one direction, as written. Worth recording that "an unreadable `--body-file`" is the sentence under which New-6's false-negative half hides: the promise is kept, and keeping it is what lets a receiptless PR through in the one-call shape. Not a defect on its own; it belongs in the New-6 fix note, not a separate fix.

4. **FORK — `verification.md:7-9` still omits the agent the hook fires on.**
   > `Consumers: \`/we:orchestrate\` (once at` / `integration, before the PR), \`/we:story\` (emits the plan's verification section),` / `\`we:ac-reviewer\` (checks the receipt exists and matches).`

   `pr-creator` moves the receipt and is the only agent the gate denies. Cosmetic now that `integration-pipeline.md:81-82` and `pr-creator.md:65-66` both bind it; `verification.md` was not in this revision's scope.

## Grade

**4** — measured against the rubric's two clauses.

*"Denies no command that opens no PR"*: 46 of 46 allowed. Every delimiter style, both `tee`
spellings, `python3 - <<PY`, `git commit -F -`, subshells, brace groups, nested and repeated
heredocs, `xargs`, `awk`, `sed`, a `--body` that legitimately contains the words, a `--body` full
of code spans, and a document whose example is newline-separated. Round 1's regression and round
2's narrowed remnant are both closed and both pinned (`test:339`, `test:344`, `test:348`,
`test:353`). That was the expensive direction and it is genuinely fixed.

*"The receipt reaches the PR body without a denial"*: it does on the cold trace — one attempt,
zero denials — but not on the retry path. New-6 denies a PR whose body carries the receipt when
the body file is rewritten and `gh` invoked in one Bash call, and `pr-creator.md:71-72` spends the
only retry on it. The fix for round 2's New-4 and this new false positive shipped together, on the
same line, with no test on the seam — the exact pattern round 2 flagged when `test:195` pinned the
`&&` separator that worked. Not a 3, because the defect is one clause of two, on one command
spelling, and the gate's behaviour on every other shape improved; not a 5, because a gate that
blocks a correct PR is the failure mode this hook's own docstring calls the expensive one.
