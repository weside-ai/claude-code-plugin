# Round 1 — Scenario D: refiner whose plan fails the DoR scan once

Table-top simulation. Nothing was executed; no plan file was written. Every tool call
below is one I *would* have made, in order, with the arguments I would have passed.

Skill under test: `we/skills/refine/SKILL.md` (SIM-1-p1 checkout).
Scan implementation: `we/scripts/orchestration.py` § `_body_is_refined` (line 2785).
Note: the SKILL and `dor-scan.md` both call the runner `orchestration.py` /
`${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py`; the file actually lives at
`we/scripts/orchestration.py`. I found it by `find`, not by following the reference.

---

## Trace (pass 1)

**Step 0 — load the instruction set.**
`Skill(skill="refine")`. Brief says "That skill is your instruction set". No decision.

**Step 1 — parse the hard rules against my brief.**
Reading `## Hard rules`, I resolve four things before touching a tool:

- *"Write the plan file. Run nothing else."* → my whole toolbelt collapses to
  Read/Glob/Write plus the ticketing MCP and one SendMessage. No `Bash`, so no
  `ls`, no `grep`, no `cat`.
- *"Never enter plan mode."* → matches the brief. No decision.
- *"Opus writes the plan."* → I am already Opus (the Lead spawned me `model="opus"`).
  This bullet is a no-op for the dispatched path, which is the *only* path the brief
  puts me on. First `[CUT]` candidate logged.
- *"A genuine design fork stops you."* → world state says the context is complete.
  I check anyway when reading the architecture doc (Step 3). No fork found → proceed.

**Decision I had to make here:** does "Run nothing else" forbid `Glob`? The skill later
tells me to "check `.markdownlint*` before assuming 80" — which needs a directory
listing. I resolve it as *shell* commands being banned, not read-only file tools, and
use `Glob`. That reconciliation is mine, not the skill's. → Defect 4.

**Step 2 — Workflow item 1: read the architecture reference the brief names.**

```
Read(file_path="/home/dev/acme/docs/architecture/observability.md")
```

**Step 3 — read the code the story will touch.**

```
Read(file_path="/home/dev/acme/src/obs/formatter.py")
Glob(pattern="src/**/*queue*.py")        # the brief names "the queue producer and
Glob(pattern="src/**/*worker*.py")       # consumer" but gives me no file paths
Read(<the producer file the globs surface>)
Read(<the consumer/worker entrypoint>)
```

**Decision:** the brief's scope boundary is prose ("the queue producer and consumer"),
not paths, and Workflow item 1 says to read "the files the story will touch" — so I
have to *discover* them. The skill never says the brief may hand me prose scope and
never says how to turn prose into the `**Files:**` lists that Phase blocks require and
that the Lead's disjointness check reads. I invented the glob step. → Defect 5.

**Step 4 — read the repo's test discipline.**

```
Read(file_path="/home/dev/acme/.weside/config.json")   # {"test_discipline": "tdd"}
```

**Decision:** the skill says `## Testing Requirements` must be "at the level
`.weside/config.json`'s `test_discipline` asks for". It never says what `tdd` *asks
for*, and neither does `dor.md` (which only lists "Which test types? Edge cases?").
I invented the semantics: tests written first, red before green, per AC. → Defect 6.

**Step 5 — Workflow item 2: the ticket and its comments.**

```
mcp__plugin_we_weside-mcp__discover_tools(...)        # ticketing detection, ref/ticketing.md
mcp__plugin_we_weside-mcp__execute_tool(name="JIRA_GET_ISSUE",
    arguments='{"issueIdOrKey": "LOG-19", "expand": "renderedFields,comment"}')
```

Result: one comment, repeating the description. No conflict with the brief.

**Decision:** `ticketing.md` says "when a comment contradicts the description … you
name the conflict **to the user**". There is no user. The refine skill's item 2 says
"you name the conflict rather than silently picking" and stops there — no channel, no
"put it in `## Design Decisions`", no "block". Here it cost nothing (no conflict), but
the instruction is unexecutable as written in the dispatched case. → Defect 7.

**Step 6 — markdownlint reconnaissance.**

```
Glob(pattern=".markdownlint*")     # none → I apply the skill's defaults: wrap at 80,
                                   # blank line before every list incl. after **Files:**
```

**Step 7 — write the plan.**

```
Write(file_path="/home/dev/acme/docs/plans/LOG-19-story.md", content=<plan>)
```

Frontmatter I wrote:

```yaml
---
story: LOG-19
epic: <the epic key — the brief gave me an epic *frame* in prose, no key>
created: 2026-08-27
status: draft
parallel_groups: []
---
```

**Decision:** the skill demands frontmatter `story`, `epic`, `created`, `status: draft`.
`docs/plan-format.md`'s frontmatter table has **no `epic` field at all** (`story`,
`created`, `status`, `parallel_groups`), and my brief gave me an epic as a sentence of
prose, not a key. I invented a slug. → Defect 8.

Sections written, in the order the skill lists them, all present: `## Context`
(~120 words), `## Acceptance Criteria` (4), `## User Journey`, `## Testing
Requirements`, `## Technical Approach`, `## Implementation Phases` (3 phases, each
with a real `**Files:**` list), `## Design Decisions`, `## Code Guidance`,
`## Security Review Required`, `## Documentation Impact`.

Phase headers I wrote — and this is the trap:

```markdown
### Phase 1: Stamp the correlation id onto the enqueued job
```

I wrote the colon-plus-title form because `docs/plan-format.md` mandates
`^### Phase (\d+): (.+)$`. **The SKILL's own example does not have it** — it writes
"`### Phase 1`, `### Phase 2`, …". A refiner who follows the skill literally and
never opens `plan-format.md` writes headers that `dor-scan.md`'s published regex
(`^### Phase [0-9]+:`) rejects. They happen to survive because the *code* is
`^### Phase \d+`. Three specs, three different phase headers. → Defect 3.

And the ACs, as the world state stipulates:

```markdown
1. **Given** a queued job carrying a correlation id **when** the consumer picks it up
   **then** every log line it emits carries that id
2. **Given** an HTTP request with no inbound id **when** work is enqueued **then** a
   fresh UUID4 is minted and stamped on the job
3. **Given** a job whose payload holds PII **When** it is logged **Then** the
   formatter emits the id and not the payload
4. **Given** a consumer crash mid-job **when** the retry runs **then** the same
   correlation id is reused
```

**Step 8 — report.**

```
SendMessage(to="team-lead", summary="refiner-LOG-19 done",
            message="wrote docs/plans/LOG-19-story.md")
```

**Decision:** `summary="refiner-{TICKET} done|blocked"` is a literal with a pipe; I
pick `done`. Fine. I did **not** re-read my own file, because
*"Don't claim the plan is refined and don't run the DoR scan on your own output"*
plus *"Run nothing else"* read together as "hands off your output". That is exactly
how the defect ships. → Defect 2.

---

### Trace question (1): did the skill warn me, and would it have stopped me?

It warned me *loudly* — six lines, an anecdote, a date, a bolded imperative:

> **Capitalise all three keywords, every time.** The Definition-of-Ready scan matches
> the literal strings `Given`, `When` and `Then`; a lowercase `**when**` mid-sentence
> reads perfectly and leaves the plan stuck in `draft` with no error message anywhere.

Would it have stopped me? **No — and the reason is worse than silence: the stated
mechanism is false.** The code is:

```python
if "Given" not in text or "When" not in text or "Then" not in text:
    return False
```

A plain substring test over the **entire document**. Not per-AC, not word-boundary,
not bold-aware. Consequences, all verifiable from that one line:

- With three of four ACs lowercased and AC 3 correct, `_body_is_refined` **passes**.
  My pass-1 file, exactly as the world state describes it, is refined by the code.
- One capitalised `When` anywhere — a Context sentence beginning "When the consumer
  picks the job up…", a Testing Requirements bullet, the word `Then` inside a code
  fence — satisfies the gate with zero valid ACs.
- Conversely, a plan with four perfect ACs and no `## Context` header fails with the
  same silence, and the skill's warning aims all its attention at the wrong check.

So a refiner who *reads the code the skill points at* concludes the warning is
overstated, and one who reads only the skill obeys a rule the gate does not enforce.
The skill also contradicts its own reference: `dor-scan.md` says "at least one
occurrence of `Given` AND `When` AND `Then`" — **accurate** to the code. The SKILL is
the drifted document. → Defect 1.

(Whether the Lead's pass-1 scan can even fail on "three of four" depends on there
being no capitalised `When`/`Then` anywhere else in a ~900-word plan — unlikely in
practice. The scenario's failure is real only under the skill's *claimed* semantics,
which is itself the finding.)

### Trace question (2): who catches it, and how long

Not me — the skill forbids it. The chain:

1. My `Write` lands. (t₀)
2. My `SendMessage` sits until the Lead's **turn boundary** — `orchestration.md`:
   a message lands when the current turn ends, minutes if the Lead is deep in a
   tool chain.
3. Lead runs the scan itself (`orchestrate/SKILL.md` line ~288: *"On the report: run
   the DoR scan yourself"*).
4. Fails → *"re-dispatch **once** with the missing item"*.
5. New Agent spawn, full context re-read, full plan rewrite, second report, second
   turn boundary, second scan.

That is two full Opus refiner spawns and two Lead turn boundaries for a capitalisation
slip that a single `Read` of my own output would have caught in seconds. And the budget
is hard: orchestrate line 289 — *"still failing → Decision Queue"*. **One** retry. A
second slip parks LOG-19 for a human. The skill spends six lines describing this
failure class and zero lines letting anyone downstream of the Write catch it before the
Lead's turn.

---

## Trace (pass 2)

Input: same brief plus `MISSING: DoR scan failed — ACs did not match the GWT tokens.`

**Step 0.** `Skill(skill="refine")` again. I search the skill for anything about being
re-dispatched, an existing file, or a `MISSING:` line. **There is nothing.** The word
"again", "existing", "rewrite", "re-dispatch" and "MISSING" do not appear. Everything
below is invention.

**Step 1 — do I look at what is there?**

```
Read(file_path="/home/dev/acme/docs/plans/LOG-19-story.md")
```

**Decision, invented:** Workflow item 3 says only *"**Write the file** at
`docs/plans/{TICKET}-story.md`"* — which reads as "produce it", i.e. from scratch. But
`Write` on an existing file needs a prior `Read` in this harness, and blowing away a
substantively-correct plan over four capital letters is destructive. I read first.
A cheaper refiner following the skill literally would re-run Steps 2–7 of pass 1 —
every architecture Read, every glob, the ticket fetch — and regenerate the whole plan,
paying the full pass-1 cost and risking a *different* plan for the same story. The
skill has no opinion. → Defect 9.

**Step 2 — patch or rewrite?** I choose the minimal edit:

```
Edit(file_path="/home/dev/acme/docs/plans/LOG-19-story.md",
     old_string="**when** the consumer picks it up **then**",
     new_string="**When** the consumer picks it up **Then**")
Edit(... AC 2 ...)   # same substitution
Edit(... AC 4 ...)   # same substitution
```

Three Edits. Nothing in the skill sanctions `Edit` at all — the hard rule is "**Write**
the plan file", and the section is titled "What you write". Using `Edit` is me deciding
the rule means "produce the file", not "call the Write tool". → Defect 9.

**Step 3 — the frontmatter questions nobody answers.**

- `created:` — still `2026-08-27`, or re-stamped? `plan-format.md` says it feeds
  "stale-plan detection". The refine skill says `created` and stops. I kept it.
- `status:` — the skill says write `status: draft`, full stop. `plan-format.md` and
  `dor.md` say `approved` comes "after `/we:story` Step 5" — a step this skill does
  **not** have. So a plan produced by `/we:refine` can never leave `draft`, in any
  number of passes.
  The trap underneath: `orchestrate/SKILL.md` line 129 reads
  `| draft | plan exists but fails the scan | **REFINE** |` — and that lane state comes
  from `_body_is_refined(text)`, **not** from the frontmatter. A refiner who reads
  those two documents together and "fixes" the loop by writing `status: approved`
  changes nothing about the gate and silently lies in the file. The refine skill never
  says the frontmatter `status` and the lane `draft` are different things. → Defect 10.

**Answer to trace question (3): no.** Pass 2 is entirely unspecified — rewrite vs
patch, re-read or not, `created`, and whether `status: draft` still holds. Four
invented decisions in a pass whose whole content is one substitution.

**Step 4 — report.**

```
SendMessage(to="team-lead", summary="refiner-LOG-19 done",
            message="wrote docs/plans/LOG-19-story.md")
```

**Decision, invented:** the message template is fixed prose — "wrote
docs/plans/…". I *want* to say "capitalised GWT tokens in ACs 1, 2, 4; no other
change", because the Lead is about to scan and, if it fails again, must decide
between one more try and the Decision Queue with no information about what I changed.
The template has no slot for it. I appended the note anyway, breaking the template.
→ Defect 11.

---

### Trace question (4): does the skill's wording match `_body_is_refined`?

**No — all three checks drift, across four documents.**

| Check | `_body_is_refined` (code) | `dor-scan.md` | `plan-format.md` | `refine/SKILL.md` |
|---|---|---|---|---|
| Phase header | `^### Phase \d+` — **no colon**, no title | `^### Phase [0-9]+:` | `^### Phase (\d+): (.+)$` | example `### Phase 1` — no colon, no title |
| Context | `> 50` **non-whitespace chars**, section bounded at the next `^##` | "> 50 characters of actual content" | "non-empty (> 50 characters)" | "a real narrative brief, **over 50 words**" |
| GWT | substring, **document-wide**, case-sensitive | "at least one occurrence of `Given` AND `When` AND `Then`" | "in the AC section" | per-AC, all three capitalised, every AC |

Two rows are load-bearing:

- **Phase header:** the skill's own example violates both *documented* regexes while
  passing the code. Copy the skill, and you ship a header the published contract
  rejects and the implementation accepts — the worst possible combination, because
  nothing red ever appears until someone tightens the regex to match its own docs.
- **Context:** "over 50 words" vs ">50 characters" is an order of magnitude. The skill
  is stricter, so it fails safe — but a refiner reasoning about *why* their plan failed
  is reading a threshold that is wrong by 10×. Also undocumented anywhere except the
  code: the section is cut at the next `##` header, and whitespace does not count.
- **GWT:** covered in question (1). `dor-scan.md` is right; the SKILL is wrong.

`dor-scan.md` closes with *"the wording here and the code must not drift."* It hasn't.
The SKILL, which is the document a refiner actually reads, has — and no line tells a
refiner that `dor-scan.md` outranks the SKILL's gloss of it.

---

## Conformance checklist

| Brief / skill requirement | Pass 1 | Pass 2 |
|---|---|---|
| Ran `Skill(skill="refine")` | yes | yes |
| Wrote `docs/plans/LOG-19-story.md` | yes | edited it |
| No `git`, no `gh`, no `orchestration.py`, no shell | yes | yes |
| No `EnterPlanMode`/`ExitPlanMode` | yes | yes |
| Did not run the DoR scan on my own output | yes | yes |
| Did not claim the plan passed | yes | yes |
| Exactly one `SendMessage` to `team-lead` | yes | yes |
| `summary` matched the template | yes | yes |
| `message` matched the template | yes | **no** — appended what changed (Defect 11) |
| Read architecture refs before writing | yes | not re-read |
| Read the ticket **with comments** | yes | skipped (invented) |
| All 10 required sections present | yes | unchanged |
| Frontmatter per skill (`story`,`epic`,`created`,`status`) | yes, `epic` invented | unchanged |
| Phases with concrete `**Files:**` lists | yes | unchanged |
| Markdownlint-safe (80 cols, blank line before lists) | yes | unchanged |
| **Plan actually passes the documented gate** | **no** (per the skill's semantics) | yes |

---

## Skill defects

**1. `[CLARITY]` — the skill's description of the gate does not match the gate.**

> "The Definition-of-Ready scan matches the literal strings `Given`, `When` and `Then`;
> a lowercase `**when**` mid-sentence reads perfectly and leaves the plan stuck in
> `draft` with no error message anywhere."

The code is `if "Given" not in text or "When" not in text or "Then" not in text` — one
document-wide substring test. A single capitalised `When` anywhere in the file (Context
prose, a test bullet, a code fence) passes the gate with zero valid ACs, and three
lowercased ACs out of four do **not** fail it; the SKILL also contradicts its own
`dor-scan.md`, which states the code's semantics correctly. Fix: state the real rule —
"the gate only checks the three tokens appear *somewhere*; capitalise them in every AC
because reviewers and `/we:develop` read the ACs, not because the scan will catch you."

**2. `[MISSING MECHANIC]` — the one failure class the skill documents in detail is the
one it forbids anyone reachable to catch.**

> "**Write the plan file. Run nothing else.**"
> "**The Lead verifies, not you.** Don't claim the plan is refined and don't run the DoR
> scan on your own output"

The second line conflates three distinct acts — *running the scan*, *claiming a pass*,
and *looking at your own file* — and the first removes the `grep` that would make a
token check trivial, so the refiner writes and stops with no self-inspection at all;
the miss then costs two Opus spawns and two Lead turn boundaries, against a hard budget
of one retry before the Decision Queue. Fix: add one line — "before reporting, `Read`
the file back and confirm each AC carries capitalised `Given`/`When`/`Then` and that
`## Context` exceeds 50 words; that is proofreading, not the scan, and not a claim."

**3. `[CLARITY]` — the skill's phase-header example contradicts both published specs.**

> "`## Implementation Phases` — `### Phase 1`, `### Phase 2`, … each with a concrete
> `**Files:**` list."

`dor-scan.md` publishes `^### Phase [0-9]+:` and `plan-format.md` publishes
`^### Phase (\d+): (.+)$` — both require a colon and a title, which the skill's example
omits; a refiner copying it writes headers that the documented contract rejects and only
the implementation (`^### Phase \d+`) accepts. Fix: write the example as
`### Phase 1: <title>` and say the colon-and-title form is required by `plan-format.md`.

**4. `[CLARITY]` — "Run nothing else" collides with an instruction that needs a listing.**

> "**Write the plan file. Run nothing else.** No `git`, no `gh`, no `orchestration.py`,
> no checkpoint, no commit."
> "If the repo ships a config, its numbers win over these; check `.markdownlint*` before
> assuming 80."

Checking `.markdownlint*` requires at minimum a `Glob`, and in the permission mode the
same paragraph warns about ("teammate Bash denied outright") it is unclear whether the
prohibition is on shell commands or on all non-Write tools — I had to rule on it myself.
Fix: rewrite the rule as "no shell commands and no state mutation; Read/Glob/ticketing
are yours."

**5. `[MISSING MECHANIC]` — no route from prose scope to the `**Files:**` lists the rule
calls load-bearing.**

> "each with a concrete `**Files:**` list. Those lists are what the Lead's disjointness
> check reads before it dares run two workers at once; vague ones make the check lie."

The brief legitimately hands scope as prose ("the queue producer and consumer"), and
Workflow item 1 says to read "the files the story will touch" without saying how to find
them when the brief names none — I invented a `Glob` sweep, and a different refiner
would invent a different file set for the same story. Fix: add a workflow line —
"if the brief names scope in prose, resolve it to paths by `Glob`/`Read` first, and list
the resolved paths in `## Technical Approach` so the Lead can audit the resolution."

**6. `[MISSING MECHANIC]` — `test_discipline` is read but never interpreted.**

> "`## Testing Requirements` — per AC, at the level `.weside/config.json`'s
> `test_discipline` asks for."

Neither the skill, `dor.md`, nor `plan-format.md` says what any value of
`test_discipline` asks for, so with `"tdd"` in hand I invented "tests first, red before
green, one per AC" — and a cheaper refiner will invent something else. Fix: give the
mapping inline (`tdd` → tests precede code and each AC names its red test;
`test-after` → coverage per AC; `none` → smoke only) or point at the file that holds it.

**7. `[CLARITY]` — "name the conflict" has no recipient in the dispatched case.**

> "corrections and scope cuts live there, newest wins, and you name the conflict rather
> than silently picking (`references/ticketing.md`)."

The referenced `ticketing.md` says to name it "to the user", and this skill's premise is
"**There is no user to ask**" — so a real ticket/brief conflict leaves the refiner with
an instruction it cannot execute and no stated channel (blocked report? `## Design
Decisions`? `## Context`?). Fix: say where it goes — "record both statements in
`## Design Decisions`, build the newest, and add `| conflict: <one line>` to the report".

**8. `[CLARITY]` — the frontmatter contract disagrees with `plan-format.md`.**

> "The frontmatter (`story`, `epic`, `created`, `status: draft`) and these sections."

`plan-format.md`'s frontmatter table lists `story`, `created`, `status`,
`parallel_groups` and has **no `epic` field**, and my brief supplied the epic as a
sentence of prose with no key — so I invented a slug for a field one spec demands and
the other does not document. Fix: align the two, and say what to write when the brief
gives an epic frame but no key (omit the field).

**9. `[MISSING MECHANIC]` — nothing covers being re-dispatched over a file that already
exists.**

> "3. **Write the file** at `docs/plans/{TICKET}-story.md`."

The word "existing" never appears in the skill, so on pass 2 I decided alone to `Read`
first, to `Edit` rather than `Write` (a tool the skill never sanctions), to skip the
architecture and ticket reads, and to keep `created:` unchanged — four inventions for a
pass whose entire content is one substitution, and a literal reader regenerates the whole
plan at full cost. Fix: add a short "Re-dispatched?" paragraph — re-read the file, fix
only the named `MISSING:` item, leave `created:` alone, and say in the report what
changed.

**10. `[MISSING MECHANIC]` — `status: draft` is a dead end and collides with the lane
name.**

> "The frontmatter (`story`, `epic`, `created`, `status: draft`)"

`plan-format.md` and `dor.md` say `approved` is set "after `/we:story` Step 5", a step
`/we:refine` does not have, so a refined plan stays `draft` forever; meanwhile
`orchestrate/SKILL.md` line 129 names the *lane* `draft` = "plan exists but fails the
scan", and that lane is computed by `_body_is_refined`, **not** by the frontmatter — a
refiner who tries to escape the loop by writing `status: approved` changes nothing and
puts a false claim in the file. Fix: one line — "frontmatter `status` stays `draft`; the
lane the Lead reads comes from the body scan, not this field."

**11. `[CLARITY]` — the report template has no slot for what changed on a re-run.**

> "`message="wrote docs/plans/{TICKET}-story.md | blocked: <the fork>"`"

On a re-dispatch the Lead is one scan away from either accepting the plan or sending it
to the Decision Queue and gets no signal about what I actually changed, so I broke the
template to add it. Fix: `message="wrote … | fixed: <the MISSING item> | blocked: <fork>"`.

**12. `[CUT]` — the model-tier bullet is inert on the only path that matters.**

> "**Opus writes the plan.** A dispatched refiner is spawned on `opus` by the Lead
> (model-tier rule: `${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md`); invoked
> standalone on a cheaper session model, name it once and suggest `/model opus` — then
> proceed either way."

A dispatched refiner cannot change its own model and is already on Opus, so the whole
bullet is addressed to a case the skill is not being run in; "then proceed either way"
makes it a no-op even in the standalone case. Fix: cut to one clause in the description,
or move it to `worker-dispatch.md` where the Lead reads it.

**13. `[CUT]` — three lines that restate the job to a model that already does it.**

> "Draft in your head, write the file."
> "A plan written without opening the seam it plans to change is a guess in plan format."
> "`## Technical Approach` — the patterns and files, reuse over rebuild."

None of these changed a single tool call I made; an Opus refiner reads the referenced
code and prefers reuse unprompted. Fix: delete, and spend the lines on defects 2 and 9.

---

## What I needed and did not find

1. **A permitted proofread.** The skill's most-emphasised failure mode is invisible to
   its author by construction. One `Read`-back with three named checks closes it and
   violates nothing the skill actually cares about (no scan, no claim).
2. **Pass-2 rules.** Re-dispatch is a first-class state in `orchestrate` (line 289) and
   does not exist in `refine`. Four invented decisions.
3. **A true statement of the gate**, or an instruction that `dor-scan.md` outranks the
   skill's gloss. Right now the SKILL is the drifted copy of its own reference.
4. **One phase-header form** across code, `dor-scan.md`, `plan-format.md` and the skill.
5. **The `test_discipline` mapping**, and a rule for turning prose scope into `**Files:**`.
6. **Where a brief-vs-ticket conflict goes** when there is no user.

---

## Grade

**2/5.** The skill's spine is sound — the hard rules are the right hard rules, the
section list is complete, and the markdownlint paragraph is genuinely earned operational
knowledge. But grade follows question (3), and pass 2 is where a fresh refiner invents
most: re-read or not, patch or rewrite, `created`, `status` — four decisions in a pass
containing one substitution, none of them mentioned anywhere in the skill, and all of
them taken under a one-retry budget before the story goes to a human. Layered on that,
the skill's single most emphatic instruction misdescribes the code it points at (Defect
1), its own phase example violates both published regexes (Defect 3), and the failure it
spends six lines and a dated anecdote on is one it structurally forbids anyone reachable
to catch (Defect 2) — so its most confident paragraph is also its least reliable. Add
the prose-to-`**Files:**` gap and the uninterpreted `test_discipline`, and I invented or
reconciled a step at seven points across two passes. It is a usable skill for a strong
model on a clean first pass; it is not a skill a fresh refiner follows without inventing
a step, and the retry path — the one this scenario exercises — is unwritten.

**Body should grow**, but not by much and not evenly: roughly +15 lines (a
"Re-dispatched?" paragraph, a permitted proofread line, the `status`/lane note, a
prose-to-paths line, the `test_discipline` mapping), paid for by ~10 lines of cuts
(Defects 12 and 13) and by *shortening* the GWT paragraph to something true. Net near
zero, with the accuracy of the three specs — code, `dor-scan.md`, `plan-format.md`,
skill — reconciled to one wording first, because no amount of added prose helps while
the four documents describe four different gates.
