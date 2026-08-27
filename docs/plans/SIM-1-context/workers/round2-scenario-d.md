# Round 2 — Scenario D: refiner whose plan fails the DoR scan once

Table-top only. Nothing executed, no plan file written, nothing edited. Every tool call
below is one I *would* have made, in order.

Skill under test: `we/skills/refine/SKILL.md` (SIM-1-p1, 7727 bytes; round 1 was 6506).
Gate implementation: `we/scripts/orchestration.py` — `_PHASE_HEADER_RE` (line 2670),
`_body_is_refined` (line 2785).

---

## Trace (pass 1, revised skill)

**Step 0 — load the instruction set.** `Skill(skill="refine")`.

**Step 1 — parse the hard rules.** Round 1's first invented decision is gone. The rule now
reads:

> "**Mutate nothing but the plan file.** Reads are expected — files, `Glob`, `Grep`, the
> ticket — but no shell: no `git`, no `gh`, no `orchestration.py`, no checkpoint, no commit."

`Glob` and `Grep` are named as permitted. No reconciliation needed, and the later
`.markdownlint*` instruction ("`Glob` for `.markdownlint*` before assuming 80") no longer
collides with anything. Zero decisions here.

Second hard rule I resolve up front:

> "**The Lead verifies, not you.** Reading your own file back is proofreading and expected;
> running the DoR scan on it, or claiming it passed, is not."

Round 1 read the equivalent line as "hands off your output". This one separates the three
acts explicitly. I plan a read-back.

Fork rule: world state says the context is complete. I check while reading the architecture
doc; no fork. `## Open Fork` is not written.

**Step 2 — Workflow item 1: the ticket and its comments.** Note the ordering flip — the
ticket is now item 1, ahead of the architecture reads, "an open question there can end the
run before you spend anything." Cheaper ordering, and correct.

```
mcp__plugin_we_weside-mcp__discover_tools(...)            # references/ticketing.md
mcp__plugin_we_weside-mcp__execute_tool(name="JIRA_GET_ISSUE",
    arguments='{"issueIdOrKey": "LOG-19", "expand": "renderedFields,comment"}')
```

One comment, repeating the description. No conflict. Had there been one, the skill now
tells me where it goes — round 1's dead end is closed twice over:

> "Newest statement wins; you name the conflict in `## Design Decisions` rather than
> silently picking."
> "`## Design Decisions` … A ticket comment that contradicts the brief goes here, both
> statements named, newest built."

**Step 3 — Workflow item 2: architecture refs, then the code.**

```
Read(file_path="/home/dev/acme/docs/architecture/observability.md")
Read(file_path="/home/dev/acme/CLAUDE.md")
Read(file_path="/home/dev/acme/src/obs/formatter.py")
Grep(pattern="enqueue|Queue\\(|rq\\.", path="src", output_mode="files_with_matches")
Glob(pattern="src/**/*worker*.py")
Read(<producer>) ; Read(<consumer entrypoint>)
```

No invention. The prose-scope gap from round 1 is written down:

> "When the brief gives scope as prose ('the queue producer and consumer'), resolve it to
> real paths with `Glob`/`Grep` first and say in `## Technical Approach` how you resolved
> it, so the Lead can audit it."

The example in that sentence is *literally my brief's phrase*. I resolve the four paths and
record the resolution in `## Technical Approach`.

**Step 4 — test discipline.**

```
Read(file_path="/home/dev/acme/.weside/config.json")     # {"test_discipline": "tdd"}
Read(file_path="${CLAUDE_PLUGIN_ROOT}/references/test-discipline.md")
```

The skill now names the owner instead of leaving the term undefined:

> "`## Testing Requirements` — per AC, at the level `test_discipline` asks for
> (`references/test-discipline.md` owns what each level means)."

And that file has the table (line 19): `tdd` = "Red before green wherever a seam exists …
One seam, one test, one minimal implementation per cycle." Round 1 invented this semantics;
round 2 reads it. I also pick up "record them in the plan when running autonomously" for the
seam list (line 28) — which is exactly my case.

**Step 5 — markdownlint recon.** `Glob(pattern=".markdownlint*")` → none → 80 columns,
blank line before every list including after `**Files:**`. Unchanged from round 1 and still
the best-earned paragraph in the file.

**Step 6 — write the plan.**

```
Write(file_path="/home/dev/acme/docs/plans/LOG-19-story.md", content=<plan>)
```

Frontmatter: the skill no longer enumerates fields. It says

> "Frontmatter and section semantics are owned by `docs/plan-format.md` — follow it, and
> leave `status: draft` alone: the lane the Lead reads is computed from the body, not from
> this field, so writing `approved` changes nothing and puts a false claim in the file."

So I write exactly `plan-format.md`'s block — `story`, `created`, `status`,
`parallel_groups`. **No `epic:` field, so no invented slug.** Round 1's Defect 8 cannot
happen: the skill stopped asking for a field its own reference does not define.

Phase headers, from the skill's own example this time:

```markdown
### Phase 1: Stamp the correlation id onto the enqueued job
```

`### Phase 1: <title>` satisfies the code (`^### Phase \d+`), `dor-scan.md`
(`^### Phase [0-9]+:`) and `plan-format.md` (`^### Phase (\d+): (.+)$`) simultaneously. The
skill now writes the intersection of all three specs. No trap.

**And the ACs — the world state's stipulation still fires.** The AC bullet reads:

> "**Capitalise all three keywords in every AC.** The scan only checks that the three tokens
> appear *somewhere* in the file, so it will not catch a lowercase `**when**` — the reviewer
> and `/we:develop` will, and a plan whose ACs read as prose is unbuildable."

This is a drafting-time instruction, and drafting-time instructions did not stop me in round
1. It does not stop me here either. I write:

```markdown
1. **Given** a queued job carrying a correlation id **when** the consumer picks it up
   **then** every log line it emits carries that id
2. **Given** an HTTP request with no inbound id **when** work is enqueued **then** a fresh
   UUID4 is minted and stamped on the job
3. **Given** a job whose payload holds PII **When** it is logged **Then** the formatter
   emits the id and not the payload
4. **Given** a consumer crash mid-job **when** the retry runs **then** the same correlation
   id is reused
```

**Step 7 — Workflow item 3, the new one. This is where the fix lands.**

> "3. **Write the file** at `docs/plans/{TICKET}-story.md`, then read it back once and check
> three things: every AC carries capitalised `Given`/`When`/`Then`, `## Context` is a real
> paragraph, and every `### Phase N:` header has a `**Files:**` list."

```
Read(file_path="/home/dev/acme/docs/plans/LOG-19-story.md")
```

Check 1 is verbatim my defect. Reading the AC block back as a discrete verification act —
rather than re-reading my own prose for sense — I see `**when**` in 1, 2 and 4 and fix them
before reporting. **The revised skill stops me at line 91-93, not at line 51-53.** The
warning does not work; the read-back does. That is the correct division of labour, and it is
what round-1 Defect 2 asked for.

One residual: the check is an eyeball. `Grep` is permitted by the hard rules and would make
it deterministic (`Grep(pattern="\\*\\*(when|then|given)\\*\\*", path=<the plan>)` — zero
hits or bust). The skill names the checks but not the instrument. See new defect B.

**Step 8 — report.**

```
SendMessage(to="team-lead", summary="refiner-LOG-19 done",
            message="wrote docs/plans/LOG-19-story.md")
```

The template now carries optional slots (`| fixed: … | conflict: …`), both empty on a clean
first pass. No claim of passing, no scan run. Conformant.

**Pass-1 outcome under the revised skill: the plan is correct and pass 2 never fires.** The
whole scenario is disarmed by one added workflow line.

---

## Trace (pass 2, revised skill)

Pass 2 is now a **counterfactual**: it only happens if the step-3 read-back was skipped or
the eyeball missed a token. The scenario stipulates it, so I run it.

Input: same brief plus `MISSING: DoR scan failed — ACs did not match the GWT tokens.`

**Step 0.** `Skill(skill="refine")`. This time the word "Re-dispatched" *is* in the file —
Workflow item 4:

> "4. **Re-dispatched over a plan you already wrote?** The brief carries a `MISSING:` line.
> Read the existing file, fix only that item, leave `created:` and everything else as-is,
> and name what you changed in the report — do not regenerate the plan."

Every one of round 1's four inventions is answered by that sentence: read first (yes), patch
not rewrite ("do not regenerate"), `created:` unchanged ("leave `created:` … as-is"), report
what changed ("name what you changed"). Round-1 Defect 9's substance is written down.

**Step 1 — but where do I read it?** The Workflow is a numbered sequence and this is item
**4**. Item 3 is "**Write the file** … then read it back once". A literal sequential reader
does items 1, 2 and 3 — re-fetch the ticket, re-read `observability.md` and `formatter.py`,
re-`Grep` the seam, and **rewrite the plan** — and only then arrives at "do not regenerate
the plan." The branch condition is placed after the work it exists to prevent. I catch it
because I read the whole skill before acting; a refiner working the list top-down does not.
→ New defect A.

Taking item 4 as intended:

```
Read(file_path="/home/dev/acme/docs/plans/LOG-19-story.md")
```

**Step 2 — and here the retry path runs out of instructions.** The `MISSING:` line says the
ACs did not match the GWT tokens. I read the file. AC 3 carries `**Given**`, `**When**`,
`**Then**`, all capitalised. And `_body_is_refined` is:

```python
if "Given" not in text or "When" not in text or "Then" not in text:
    return False
```

A document-wide, case-sensitive substring test. With AC 3 intact, **the scan the Lead ran
cannot have failed on this item.** The named MISSING item is, as far as the code and the
skill's own truthful gate statement go, already satisfied. The skill says "fix only that
item" and has no branch for *"the named item looks correct to me"*: guess at what the Lead
actually meant and fix the other three ACs, report blocked, or push back. I guess (fix ACs
1, 2, 4 — the right guess here, and a guess nonetheless). → New defect C.

**Step 3 — patch.**

```
Edit(file_path=".../LOG-19-story.md",
     old_string="**when** the consumer picks it up **then**",
     new_string="**When** the consumer picks it up **Then**")
Edit(... AC 2 ...) ; Edit(... AC 4 ...)
```

`Edit` is still never named in the skill, but "Mutate nothing but the plan file" now sanctions
any mutation *of that file*, so this is no longer an invention — only an unnamed tool.

Frontmatter questions from round 1: all answered. `created:` — "leave `created:` … as-is".
`status:` — "leave `status: draft` alone: the lane the Lead reads is computed from the body,
not from this field." Round-1 Defects 9 and 10 both retired.

**Step 4 — do I re-run the step-3 self-check?** Nothing says so; item 3 is *behind* me in the
sequence. I do it anyway. A literal reader ships the edit unverified — the same sequencing
flaw as defect A, folded into it.

**Step 5 — report.**

```
SendMessage(to="team-lead", summary="refiner-LOG-19 done",
  message="wrote docs/plans/LOG-19-story.md | fixed: capitalised GWT tokens in ACs 1, 2, 4")
```

The template has the slot now:

> `message="wrote docs/plans/{TICKET}-story.md | fixed: <the MISSING item, if a re-run> | conflict: <one line, if any>"`

Round 1 broke the template to say this. Round 2 fills a field. Defect 11 retired.

---

## Answers to the four questions

**(1) Does the skill now describe the gate truthfully against `_body_is_refined` /
`_PHASE_HEADER_RE`?** Yes, on the mechanic that failed in round 1. "The scan only checks
that the three tokens appear *somewhere* in the file" is exactly the code's document-wide
substring test. `## Context` — "well over 50 characters" — replaces round 1's "over 50
**words**" and now matches the order of magnitude. The phase example `### Phase 1: <title>`
passes the code *and* both published regexes. Residual imprecision, non-blocking: the skill
does not say the Context threshold counts **non-whitespace** characters and that the section
is cut at the next `^##` header (lines 2801-2806), so a refiner reasoning about a marginal
Context has an approximate number, not the rule.

**(2) Does it give a permitted self-check, and would it have caught the lowercase ACs?**
Yes and yes. The permission is explicit ("Reading your own file back is proofreading and
expected") and the check is concrete (Workflow item 3, three named items, the first being
capitalised GWT per AC). It fires after the Write and before the report — the only window in
which the refiner can catch its own defect. It would have caught mine. It is an eyeball
check, not a `Grep`, on a file the same model just wrote; defect B.

**(3) Does it tell you what to do when re-dispatched over an existing file?** Yes —
Workflow item 4, covering all four of round 1's invented decisions in one sentence.
Two gaps remain: it is placed **fourth in a sequence** whose third item writes the file
(defect A), and it has no branch for a `MISSING:` item that is already satisfied (defect C).
Substance fixed, placement and edge case not.

**(4) Does anything still contradict `docs/plan-format.md`?** The skill's own text does not
— it stopped enumerating frontmatter (killing the `epic:` conflict), and its phase example
now matches the template. But the revision installs a pointer, "Frontmatter and section
semantics are owned by `docs/plan-format.md`", and that file says at lines 63-65:

> "The DoR gate scans for the presence of `Given`, `When`, and `Then` tokens **in the AC
> section** — the plan is rejected at the DoR gate if any are absent."

which contradicts the skill's (correct) "somewhere in the file", on the exact mechanic that
failed in round 1. `plan-format.md` was out of the reviser's scope, so the SKILL handles it
correctly within its own file — but **no line says which document outranks the other on gate
semantics**, and the skill just told me `plan-format.md` owns the format. That is the
cross-file fork: `plan-format.md` line 63-65 and `dor-scan.md` line 14 both need to be
reconciled to the code, or the skill needs one clause saying the gate description here is
authoritative. Minor and non-contradictory: the skill's checkbox list orders sections
Phases-before-Technical-Approach while the template runs the other way, and the prose
forward-references `## Technical Approach` from the Phases bullet.

---

## Round-1 verdict table

| # | Round-1 defect (short) | Verdict | Evidence (quoted line or its absence) |
|---|---|---|---|
| 1 | `[CLARITY]` skill's gate description ≠ the gate | **FIXED** | "The scan only checks that the three tokens appear *somewhere* in the file, so it will not catch a lowercase `**when**`" — matches `if "Given" not in text or …` exactly; the false "leaves the plan stuck in `draft`" claim is gone |
| 2 | `[MISSING MECHANIC]` no permitted self-check | **FIXED** | Hard rule: "Reading your own file back is proofreading and expected; running the DoR scan on it, or claiming it passed, is not." + Workflow 3: "read it back once and check three things: every AC carries capitalised `Given`/`When`/`Then`, `## Context` is a real paragraph, and every `### Phase N:` header has a `**Files:**` list." Catches my exact pass-1 defect |
| 3 | `[CLARITY]` phase example contradicts both specs | **FIXED** | "`### Phase 1: <title>`, `### Phase 2: <title>`, …" — satisfies `^### Phase \d+` (code), `^### Phase [0-9]+:` (`dor-scan.md`) and `^### Phase (\d+): (.+)$` (`plan-format.md`) at once |
| 4 | `[CLARITY]` "Run nothing else" vs the `.markdownlint*` check | **FIXED** | "Reads are expected — files, `Glob`, `Grep`, the ticket — but no shell". The prohibition is now on shell and mutation, not on read tools; "`Glob` for `.markdownlint*`" is consistent with it |
| 5 | `[MISSING MECHANIC]` no route from prose scope to `**Files:**` | **FIXED** | "When the brief gives scope as prose ('the queue producer and consumer'), resolve it to real paths with `Glob`/`Grep` first and say in `## Technical Approach` how you resolved it, so the Lead can audit it." Uses my brief's own phrase |
| 6 | `[MISSING MECHANIC]` `test_discipline` read but never interpreted | **FIXED** | "at the level `test_discipline` asks for (`references/test-discipline.md` owns what each level means)" — and that file's table defines `tdd`/`tests-after`/`off`. Ownership named instead of semantics invented |
| 7 | `[CLARITY]` "name the conflict" has no recipient | **FIXED** | Workflow 1: "you name the conflict in `## Design Decisions` rather than silently picking"; the section bullet repeats it; the report template carries a `conflict:` slot. Destination + channel both stated |
| 8 | `[CLARITY]` frontmatter contract vs `plan-format.md` | **FIXED** | The enumeration `(story, epic, created, status: draft)` is **absent**; replaced by "Frontmatter and section semantics are owned by `docs/plan-format.md` — follow it". No `epic:` field to invent |
| 9 | `[MISSING MECHANIC]` nothing covers re-dispatch over an existing file | **PARTIALLY** | Workflow 4 exists and answers all four round-1 inventions — "Read the existing file, fix only that item, leave `created:` and everything else as-is … do not regenerate the plan." But it sits **after** item 3's "**Write the file** … then read it back once", so a sequential reader regenerates before reaching it, and no branch covers a MISSING item that is already satisfied (defects A, C) |
| 10 | `[MISSING MECHANIC]` `status: draft` dead end / lane collision | **FIXED** | "leave `status: draft` alone: the lane the Lead reads is computed from the body, not from this field, so writing `approved` changes nothing and puts a false claim in the file" — matches `orchestrate/SKILL.md` line 128-129, where the lane comes from `_body_is_refined` |
| 11 | `[CLARITY]` report template has no slot for what changed | **FIXED** | `message="wrote docs/plans/{TICKET}-story.md \| fixed: <the MISSING item, if a re-run> \| conflict: <one line, if any>"` |
| 12 | `[CUT]` inert model-tier bullet | **FIXED** | "Opus writes the plan…" is absent; `worker-dispatch.md` is no longer referenced. ~4 lines recovered |
| 13 | `[CUT]` three lines restating the job | **PARTIALLY** | "Draft in your head, write the file." — gone. "reuse over rebuild" — gone ("`## Technical Approach` — the patterns and files."). But "A plan written without opening the seam is a guess in plan format." survives verbatim at line 90. 2 of 3 cut. In fairness it now sits as the rationale *inside* Workflow item 2 rather than floating as an aphorism, which earns it more than it earned in round 1 — but the round-1 ask was to cut it, and it is still there |

**Tally: 11 FIXED / 2 PARTIALLY / 0 STILL OPEN.**

---

## New defects introduced by the revision

**A. `[CLARITY]` — the re-dispatch branch is the fourth step of a four-step sequence, so it
fires after the work it exists to prevent.**

> "3. **Write the file** at `docs/plans/{TICKET}-story.md`, then read it back once and check
> three things…"
> "4. **Re-dispatched over a plan you already wrote?** … Read the existing file, fix only
> that item … do not regenerate the plan."

`## Workflow` is a numbered list and reads as a sequence; every other item is unconditional.
A refiner working it top-down on pass 2 re-fetches the ticket (1), re-reads the architecture
refs and re-`Grep`s the seam (2), and **rewrites the plan** (3) before item 4 tells it not
to — paying full pass-1 cost and risking a different plan for the same story, which is
precisely the failure round-1 Defect 9 asked to close. The same placement means nothing
routes the pass-2 edit back through item 3's self-check: the one verification the revision
added is behind the retry path in the reading order. Fix: hoist it to the top of the
Workflow as an unnumbered branch — "**Re-dispatched?** (a `MISSING:` line in the brief) —
skip to the existing file: read it, fix only that item, leave `created:` and everything else
as-is, re-run the checks in step 3, and name what you changed in the report."

**B. `[CLARITY]` — the self-check names three checks and no instrument, on a file the same
model just wrote.**

> "then read it back once and check three things: every AC carries capitalised
> `Given`/`When`/`Then`…"

The failure being checked for is a *drafting-instinct* defect — `**when**` mid-sentence
"reads perfectly", by the skill's own account — and the check offered against it is
re-reading your own prose. The hard rules explicitly license `Grep`, which turns check 1
into a decidable test with no self-review involved. Fix: one clause — "`Grep` the plan for
`\*\*(given|when|then)\*\*`; any hit is a lowercase keyword" — which also costs less than
the `Read`.

**C. `[MISSING MECHANIC]` — no rule for a `MISSING:` item that is already satisfied.**

> "4. … The brief carries a `MISSING:` line. Read the existing file, fix only that item"

On this scenario's retry the arithmetic does not close: `_body_is_refined` tests `"Given" not
in text or "When" not in text or "Then" not in text` document-wide and case-sensitively, so
with AC 3 fully capitalised the scan **passes**, and the Lead's
`MISSING: ACs did not match the GWT tokens` cannot have come from the code that ran. The
pass-2 refiner reads the file, finds the named item apparently correct, and has one
instruction — "fix only that item" — that it cannot execute. Guess at the Lead's intent, fix
things not named, or report blocked: unspecified, under a one-retry budget before the
Decision Queue (`orchestrate/SKILL.md` line 289-290). Fix: one line — "if the named item
already looks satisfied, do not guess: fix nothing, and report
`summary=\"…blocked\"` with `blocked: MISSING item <x> already satisfied — <what the file
actually says>`", so the Lead re-derives instead of the refiner inventing.

---

## Does the growth earn itself?

6506 → 7727 bytes, +19%. **Yes for the five mechanics, with one addition this scenario
cannot audit.**

Round-1 Scenario D named five missing mechanics (Defects 2, 5, 6, 9, 10) plus three
misstatements (1, 3, 8), which licensed growth. What was added is exactly that list, and it
is dense: the self-check is *one* clause inside an existing workflow item; the re-dispatch
rule is one sentence; the prose-to-paths rule is one sentence appended to a bullet that
already existed; `test_discipline` cost a parenthesis pointing at the file that owns it; the
`status`/lane note is a subordinate clause. Five defects for roughly nine lines, and none of
them a new section.

It was paid for, partly, out of round 1's cut list: the model-tier bullet (~4 lines) and the
frontmatter enumeration are gone, two of Defect 13's three restatements are gone, and the
GWT paragraph shrank from six lines and a dated anecdote to three truthful ones — the
shortening and the correction were the same edit, which is the best kind.

The one item Scenario D cannot credit or fault is the `## Open Fork` paragraph (lines
34-38, ~5 lines and the largest single addition): my world state has no design fork, so it
never executed in either pass, and nothing in my round-1 report asked for it. It is
plausibly earned by another scenario; from here it is simply unmeasured. Net: the growth is
concentrated where round 1 said the file was silent, and the file is more executable per
byte than it was.

---

## Grade

**4/5.** The revision fixed the two things that actually decided round 1's grade: the skill
now tells the truth about the gate it points at, and it gives the refiner a *permitted*
proofread positioned in the only window where the defect is still cheap — which, traced
honestly, is what stops my lowercase ACs. Not at line 51-53, where the drafting warning
lives and where a drafting-instinct defect was never going to be caught, but at line 91-93,
after the `Write`. On this scenario the consequence is total: pass 2 does not fire, and the
one-retry budget is never spent. Every other round-1 finding is closed too — prose scope
resolves to paths, `tdd` has an owner, a ticket conflict has a destination, the frontmatter
contradiction is gone because the skill stopped duplicating a spec it does not own, and the
phase example is now the intersection of three regexes instead of the violation of two. What
holds it off 5 is that the retry path — the path this scenario exists to exercise — is
written correctly and placed wrongly: the branch that says "do not regenerate the plan" is
the fourth item of a sequence whose third item regenerates it, and it has no answer for the
case this very scenario produces, a `MISSING:` item that the code could not have raised.
A fresh refiner following the list top-down on pass 2 still pays a full rewrite before
reading the rule against it, and then guesses. One hoisted paragraph and one "if the item
looks already satisfied, report blocked" clause is the whole distance to 5.
