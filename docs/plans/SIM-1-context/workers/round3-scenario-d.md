# Round 3 — Scenario D: refiner whose plan fails the DoR scan once

Table-top only. Nothing executed, no plan file written, nothing edited. Every tool call below
is one I *would* have made, in order.

Skill under test: `we/skills/refine/SKILL.md` (SIM-1-p1, 8327 bytes; round 2 was 7727, round 1
6506). Gate implementation: `we/scripts/orchestration.py` — `_PHASE_HEADER_RE` (line 2670),
`_body_is_refined` (line 2785).

---

## Trace (pass 1)

**Step 0 — load the instruction set.** `Skill(skill="refine")`.

**Step 1 — hard rules.** Unchanged from round 2 and still decision-free: `Glob`/`Grep`/file
reads permitted, shell and mutation-outside-the-plan-file forbidden, `EnterPlanMode` banned,
and "Reading your own file back is proofreading and expected; running the DoR scan on it, or
claiming it passed, is not." The Lead's brief says "Do not verify your own plan" — the skill
tells me which of the three acts that phrase covers. No reconciliation needed.

Fork rule: world state says the context is complete, so `## Open Fork` never fires. Unmeasured
here, as in round 2.

**Step 2 — Workflow item 0, the new first line.** Round 2's re-dispatch rule has moved from
item 4 to item **0**:

> "0. **Does `docs/plans/{TICKET}-story.md` already exist?** Then this is a re-dispatch and the
> brief carries a `MISSING:` line."

The file does not exist. One condition, false, and I fall through to item 1 having spent one
`Glob`-or-`Read`. The branch now costs a line on the happy path instead of poisoning the retry
path. Zero decisions.

**Step 3 — item 1, the ticket.**

```
mcp__plugin_we_weside-mcp__discover_tools(...)            # references/ticketing.md
mcp__plugin_we_weside-mcp__execute_tool(name="JIRA_GET_ISSUE",
    arguments='{"issueIdOrKey": "LOG-19", "expand": "renderedFields,comment"}')
```

One comment, repeating the description. No conflict; had there been one, `## Design Decisions`
is the named destination and `| conflict:` the named channel.

**Step 4 — item 2, the refs then the code.**

```
Read("docs/architecture/observability.md") ; Read("CLAUDE.md") ; Read("src/obs/formatter.py")
Grep(pattern="enqueue|Queue\\(|rq\\.", path="src", output_mode="files_with_matches")
Glob(pattern="src/**/*worker*.py")
Read(<producer>) ; Read(<consumer entrypoint>)
```

Prose scope ("the queue producer and consumer") → real paths, recorded in `## Technical
Approach`, per the rule that quotes my brief's own phrase. Unchanged from round 2, still
correct.

**Step 5 — test discipline.** `.weside/config.json` → `tdd`; `references/test-discipline.md`
owns the semantics (line 19) and asks me to record the seams in the plan when running
autonomously (line 28). Read, not invented.

**Step 6 — markdownlint recon.** `Glob(".markdownlint*")` → none → 80 columns, blank line
before every list including after `**Files:**`.

**Step 7 — write.** Frontmatter exactly `plan-format.md`'s block (`story`, `created`, `status:
draft`, `parallel_groups`), no invented `epic:`. Phase headers `### Phase 1: <title>` — the
intersection of `^### Phase \d+` (code), `^### Phase [0-9]+:` (`dor-scan.md`) and
`^### Phase (\d+): (.+)$` (`plan-format.md`).

**The world state's stipulation still fires at drafting time.** The AC bullet's warning
("**Capitalise all three keywords in every AC**") is a drafting-time instruction and does not
stop a drafting instinct — same as rounds 1 and 2. I write:

```markdown
1. **Given** a queued job carrying a correlation id **when** the consumer picks it up
   **then** every log line it emits carries that id
2. **Given** an HTTP request with no inbound id **when** work is enqueued **then** a fresh
   UUID4 is minted and stamped on the job
3. **Given** a job whose payload holds PII **When** it is logged **Then** the formatter emits
   the id and not the payload
4. **Given** a consumer crash mid-job **when** the retry runs **then** the same correlation id
   is reused
```

**Step 8 — item 3, and this is where round 3 differs from round 2.** The self-check is no
longer an eyeball:

> "3. **Write the file** …, then `Grep` it back — `Given`, `When`, `Then` capitalised in
> *every* AC, `^### Phase \d+:` for the headers, `**Files:**` under each — and read
> `## Context` to confirm it is a paragraph. Do the same after a step-0 edit."

```
Grep(pattern="\\*\\*Given\\*\\*", path=".../LOG-19-story.md", output_mode="content")
Grep(pattern="^### Phase [0-9]+:", ...) ; Grep(pattern="\\*\\*Files:\\*\\*", ...)
Read(".../LOG-19-story.md", offset=<Context>)
```

The first `Grep` returns the four AC lines **as content**, and `**when**` / `**then**` are
visible in the returned text. Caught, fixed before reporting. The mechanism is narrowing plus
inspection rather than a pass/fail test — see the residual under item B — but on this scenario
it fires.

**Step 9 — report.** `ToolSearch` for `SendMessage` (correctly told to, since it is deferred),
then one message, `| fixed:` and `| conflict:` empty.

**Pass-1 outcome: correct plan, pass 2 never fires.**

---

## Trace (pass 2)

Counterfactual — reachable only if step 3 is disobeyed. Brief plus `MISSING: DoR scan failed —
ACs did not match the GWT tokens.`

**Step 0 is now literally step 0.** The file exists → the branch is true → "Read the file, fix
only that item, leave `created:` and everything else as-is, and name what you changed in the
report — do not regenerate the plan, and skip steps 1–2." A top-down reader reaches the
prohibition **before** the ticket re-fetch, the re-`Grep` of the seam and the rewrite. Round
2's defect A is structurally gone, not merely re-worded.

```
Read(".../LOG-19-story.md")
```

**Step 1 — the item is already satisfied.** AC 3 carries `**Given**`/`**When**`/`**Then**`
capitalised, and `_body_is_refined` is a document-wide, case-sensitive substring test:

```python
if "Given" not in text or "When" not in text or "Then" not in text:
    return False
```

so the scan the Lead ran cannot have failed on this item. The skill now has the branch:

> "If the named item already looks satisfied, say exactly that in the report instead of
> guessing at a second reading; the Lead has one retry to spend."

I fix nothing and report. No guess. Round 2's defect C is answered in substance.

**Step 2 — but what shape is that report?** `summary="refiner-{TICKET} done|blocked"` is
binary, and neither message template has a field for it: one is `| fixed: … | conflict: …`, the
other is fork-shaped (`blocked: <fork> | A: … | B: … | recommend X because <why> | partial plan
at …`). "Say exactly that in the report" dictates the *content* and leaves the *routing* free,
and the routing matters: `orchestrate/SKILL.md` spends re-dispatch → still failing → Decision
Queue, so `done` and `blocked` send the Lead down different paths on its last retry. I improvise
`summary="refiner-LOG-19 blocked"`, `message="blocked: MISSING item already satisfied — AC 3
carries capitalised Given/When/Then and the scan is a document-wide substring test | no edit
made"`. → new defect D.

**Step 3 — re-check.** Had I edited, item 3's closing clause — "Do the same after a step-0
edit" — routes me back through the `Grep`s. The half of round-2 defect A that left a pass-2 edit
unverified is closed by that clause specifically.

---

## Answers to the four questions

**(1) Does the skill describe the gate truthfully?** Yes. "The scan only checks that the three
tokens appear *somewhere* in the file, so it will not catch a lowercase `**when**`" is exactly
`if "Given" not in text or "When" not in text or "Then" not in text`. `## Context` — "well over
50 characters" — is a safe overshoot of `len(non_ws) > 50` on the slice between `## Context` and
the next `^##`; the skill states neither the non-whitespace count nor the section cut, so a
refiner reasoning about a marginal Context has an order of magnitude, not the rule. Non-blocking,
unchanged from round 2. Item 3's self-check uses `^### Phase \d+:` **with** the colon while the
code is `^### Phase \d+` **without** — stricter than the gate, therefore safe, and it is
presented as the skill's own check rather than as the gate's rule, so it makes no false claim.
Same for `**Files:**`, which the gate never reads and the skill never says it does. The
`## Open Fork` paragraph's claim that such a plan "passes the 3-item scan mechanically" is also
true against the code.

**(2) Does the self-check catch the lowercase ACs, and by what mechanism?** Yes, at Workflow
item 3, by `Grep` on the written file — not by re-reading prose. Mechanism: `Grep` for the
capitalised tokens with content output returns the AC lines, and the lowercase `**when**` is
visible in the returned lines. Residual: the pattern named is the *positive* token set, which
cannot falsify "capitalised in *every* AC" — a hit proves one AC, not four. The decidable form
is the negative test (`\*\*(given|when|then)\*\*`, zero hits or bust). The reviser took round
2's instrument and not its pattern.

**(3) Does a re-dispatched refiner reach the rule before writing?** Yes. It is Workflow item 0,
ahead of the ticket read, carries its own condition ("Does … already exist?"), and explicitly
kills the intervening work ("skip steps 1–2"). A top-down reader cannot regenerate first.

**(4) What happens when the `MISSING:` item is already satisfied?** The refiner reports the
fact rather than guessing at a second reading, and the one-retry budget is named as the reason.
Content settled; report routing (`done` vs `blocked`, which slot) is not — defect D.

---

## Round-2 verdict table

| Item | Verdict | Evidence |
|---|---|---|
| Defect 9 — nothing covers re-dispatch over an existing file | **FIXED** | Hoisted to Workflow item **0**, before the ticket read: "Then this is a re-dispatch … Read the file, fix only that item, leave `created:` and everything else as-is … do not regenerate the plan, and skip steps 1–2." All four round-1 inventions plus the ordering trap answered in one block |
| Defect 13 — three lines restating the job | **PARTIALLY** | Round 2 cut two of three; round 3 trimmed the survivor from "a guess in plan format" to "a plan written without opening the seam is **a guess**" (item 2). Three words, not the sentence. It is a subordinate clause of an actionable instruction rather than a floating aphorism, which earns it more than it earned in round 1 — but the ask was to cut it |
| New A `[CLARITY]` — re-dispatch branch fires after the work it prevents | **FIXED** | Both halves. Placement: item 0 precedes items 1–3 and says "skip steps 1–2". Un-rechecked pass-2 edit: item 3 now ends "**Do the same after a step-0 edit.**", routing the retry back through the `Grep`s |
| New B `[CLARITY]` — self-check named three checks and no instrument | **FIXED** (residual) | "then `Grep` it back — `Given`, `When`, `Then` capitalised in *every* AC, `^### Phase \d+:` for the headers, `**Files:**` under each". The eyeball read-back survives only for `## Context`, where prose judgement is the right instrument. Residual: positive-token pattern cannot falsify "every AC"; the negative test would |
| New C `[MISSING MECHANIC]` — no rule for an already-satisfied `MISSING:` item | **FIXED** (substance) | "If the named item already looks satisfied, say exactly that in the report instead of guessing at a second reading; the Lead has one retry to spend." The guess round 2 was forced into is now forbidden and the budget is named. Report *shape* still unspecified → defect D |
| Cross-file fork — `plan-format.md` 63-65 vs the code | **STILL OPEN** | `plan-format.md` line 63-65 ("scans for the presence of `Given`, `When`, and `Then` tokens **in the AC section**") and its line 116 table row ("AC section non-empty") both still describe a section-scoped scan the code does not implement; `dor-scan.md` item 1 is correct. Mitigation the skill *does* provide within its own file: its pointer is scoped — "Frontmatter and **section semantics** are owned by `docs/plan-format.md`" — not to gate semantics, so the skill no longer imports the contradiction, and its own gate description is truthful. But no line in any of the three files states precedence on gate semantics. Out of the reviser's scope; the one-clause in-file close would be "the gate description here is authoritative over any other doc's" |

**Tally: 4 FIXED / 1 PARTIALLY / 1 STILL OPEN (cross-file, out of scope).**

---

## New defects

**D. `[CLARITY]` — the already-satisfied branch dictates the report's content and not its
routing.**

> "0. … If the named item already looks satisfied, say exactly that in the report instead of
> guessing at a second reading; the Lead has one retry to spend."
> "4. … `summary="refiner-{TICKET} done|blocked"`"

The summary is binary and neither message template holds this case: one is
`| fixed: … | conflict: …`, the other is fork-shaped with `A:`/`B:`/`recommend`. `done` tells
the Lead the MISSING item was addressed and the plan is ready to re-scan; `blocked` routes to
the Decision Queue after the single re-dispatch (`orchestrate/SKILL.md`, the "re-dispatch
**once** … still failing → Decision Queue" ladder). On the last retry those diverge materially,
and the skill leaves the choice to the refiner. Fix: one slot and one word — a third template
line `message="already satisfied: <the MISSING item> | the file says: <what it actually
carries> | no edit made"` under `summary="refiner-{TICKET} blocked"`.

Persisting minor, unchanged from round 2 and not worth a tag: the checkbox list orders sections
Implementation-Phases-before-Technical-Approach while `plan-format.md`'s template runs the other
way, and the Phases bullet forward-references `## Technical Approach`. The skill names
`plan-format.md` as the owner, so a refiner follows the template and nothing forks.

---

## Does the size earn itself?

**Yes.** 7727 → 8327, +600 bytes, and every byte is traceable to a round-2 finding or a
verifiable cross-file conflict:

- the item-0 hoist (defect A) — a rewrite, roughly size-neutral, paying for itself in the retry
  path it un-poisons;
- "If the named item already looks satisfied…" (defect C) — one sentence;
- "then `Grep` it back" plus the three named checks (defect B) — replaces prose of comparable
  length;
- "Do the same after a step-0 edit." (defect A, second half) — six words;
- the template-precedence sentence, "These templates extend the brief's — where the brief gives
  one slot and this gives five, send the five; a Lead reads fields, not a fixed string."

That last one is new and not asked for by round 2, and it is still earned: the Lead's refiner
brief in `orchestrate/SKILL.md` really does hand the worker a **two**-slot template
(`message="wrote docs/plans/{TICKET}-story.md | blocked: <fork/reason>"`) against the skill's
five, and without that sentence the refiner arbitrates between its dispatcher and its skill.
I hit exactly that conflict in both passes; the sentence resolves it.

The one addition this scenario still cannot audit is the `## Open Fork` paragraph (~5 lines),
same as round 2: my world state has no design fork, so it never executes. Cumulatively 6506 →
8327 (+28%) has bought seven named mechanics and shed the model-tier bullet, the frontmatter
enumeration and two of three restatements. The file is more executable per byte than either
predecessor.

---

## Grade

**5/5.** Two facts carry it. First, pass 1 is now invention-free end to end: item 0 tests a
condition and falls through, items 1–2 are read-only and fully specified, item 3's `Grep`
catches the one defect this scenario was built to plant, and item 4's template has a slot for
everything I have to say — I never had to decide anything the file did not decide for me.
Second, the retry path is no longer a trap: the "do not regenerate" rule is the first thing a
top-down reader meets, "skip steps 1–2" kills the wasted work explicitly, "Do the same after a
step-0 edit" sends the patch back through the same check, and the already-satisfied case — the
one this scenario actually produces, because the Lead's `MISSING:` line cannot have come from
`_body_is_refined` — is forbidden from being guessed at. Round 2's defect A cost a full plan
regeneration and an unverified edit; what is left in its place is a report-field choice on a
branch the fix itself made unreachable, which is a category below it. What keeps this from
being a perfect file rather than a 5: the `Grep` pattern is positive where the negative test is
decidable, the surviving "is a guess" clause was asked to go, and the gate-semantics
contradiction in `plan-format.md` 63-65 and 116 is still out there with no document declared
authoritative — none of which a fresh refiner running this scenario would trip over.
