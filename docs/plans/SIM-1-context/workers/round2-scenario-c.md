# Round 2 — Scenario C: refiner hits a genuine design fork

Table-top only. Nothing executed, no plan file written, nothing edited. Every tool
call below is the call I *would* have made, in order, against the REVISED
`we/skills/refine/SKILL.md` (7727 bytes).

## Trace (revised skill)

### Step 0 — load the skill

`Skill(skill="refine")`. Four hard rules, five workflow steps. The round-1 tension is
gone on first read:

> **Mutate nothing but the plan file.** Reads are expected — files, `Glob`, `Grep`, the
> ticket — but no shell: no `git`, no `gh`, no `orchestration.py`, no checkpoint, no
> commit.

I do not have to infer anything. Reads are licensed by name, including the ticket.

I also notice what is *absent*: the round-1 hard rule 4 ("Opus writes the plan") is
gone from the file entirely. Nothing to no-op on.

### Step 1 — the ticket, FIRST

Workflow step 1 now reads:

> 1. **Read the ticket and its comments first.** One call, and an open question there
>    can end the run before you spend anything

```
ToolSearch(query="select:mcp__atlassian__jira_get_issue")
mcp__atlassian__jira_get_issue(issue_key="CACHE-77", comment_limit=10)
```

Two comments; newest: *"ops asked: how does a catalogue edit become visible? answer
before building"*. In round 1 this arrived after two doc reads and a code survey. It
now arrives first, as intended.

The round-1 mis-fit is also gone. Step 1 no longer routes only "conflicts": "an open
question there can end the run" names exactly what I found — a question, not a
contradiction. I do not have to fall back to a hard rule by my own routing.

**But I cannot stop here**, and the skill's own text is why. See Step 2.

### Step 2 — architecture refs and the code, because the fork test demands them

The hard rule's genuineness test:

> Genuine = either branch changes user-visible behaviour no AC states, or touches a
> subsystem the scope declares OUT, or contradicts a prior decision — **and nothing in
> the brief, the ticket, the ADRs or the code settles it.**

That last clause is a read obligation. I cannot classify the ops question as a genuine
fork until I have confirmed the ADRs and the code do not answer it. So the "end the run
before you spend anything" promise does not hold for the case the rule exists for:

```
Read("/home/dev/acme/docs/architecture/api-read-paths.md")   → nothing on invalidation
Read("/home/dev/acme/docs/adr/ADR-0031-orm-boundaries.md")   → no ORM read-through; silent on invalidation
```

Then workflow step 2's locating mechanic, which round 1 had to invent:

> locate the seam from the refs and the repo's `CLAUDE.md`, then `Grep` the route or
> symbol the story names.

```
Read("/home/dev/acme/CLAUDE.md")
Grep(pattern="@router\\.get\\(\"/catalogue", output_mode="files_with_matches")
```

Two of my three round-1 invented searches are now instructed. The third — grepping for
the rate-limiter's existing Redis client — is no longer *implied* either, because the
reuse-over-rebuild prose that implied it was cut with `## Technical Approach` down to
"the patterns and files". I would still run it; the skill neither asks nor forbids.

### Step 2b — the linter check

> A repo config wins over these numbers; `Glob` for `.markdownlint*` before assuming 80.

```
Glob(".markdownlint*")  → .markdownlint.json  → line-length: 100
```

Resolves to 100 without a guess, same as round 1. Still the cleanest instruction in
the file.

### Step 3 — classifying the fork (this is where the revision pays)

I hold the two branches against the new test, mechanically:

- **(i) short fixed TTL.** Admin edits invisible until the TTL expires → *changes
  user-visible behaviour no AC states* → **genuine** on clause 1.
- **(ii) cache-bust call from the admin write tool.** → *touches a subsystem the scope
  declares OUT* ("OUT: write paths") → **genuine** on clause 2.
- Nothing in brief / ticket / ADR-0031 / api-read-paths.md settles it → the trailing
  conjunct holds.

And the rationalisation that round 1 warned would catch a less careful refiner is now
pre-empted by name:

> An *absent* constraint is not a decision: "the epic didn't fund it, so I'll do the
> cheap one" is exactly the rationalisation this rule exists to catch.

That is my exact temptation, quoted back at me. This is the single largest improvement
in the file: round 1's most dangerous outcome — a confident, beautifully formatted TTL
plan nobody approved — is now closed by an explicit test rather than by refiner
temperament.

### Step 4 — what I write (round 1 wrote nothing)

> Stopping is not writing nothing. Write the plan as far as the fork allows, leave
> `status: draft`, and add an `## Open Fork` section: the question in one line, option A
> and option B with their consequences, your recommendation and why.

So I write `docs/plans/CACHE-77-story.md` containing, concretely:

- frontmatter per `docs/plan-format.md`: `story: CACHE-77`, `created: 2026-08-27`,
  `status: draft`, `parallel_groups: []`
- `## Context` — a real paragraph (> 50 chars) on the p95 goal, the three re-queried
  tables, Redis already deployed, ADR-0031 ruling out ORM read-through
- `## Acceptance Criteria` — AC 1 is writable without the fork: **Given** a `/catalogue`
  GET that was served in the last window, **When** the same request repeats, **Then** it
  is answered from Redis without re-querying the three tables. AC 2 (the staleness
  contract) I cannot write — it *is* the fork.
- `## Implementation Phases` — `### Phase 1: Cache read wrapper at the route layer`
  with a `**Files:**` list from my Grep. Phase 2 (invalidation) has no content.
- `## Technical Approach`, `## Design Decisions`, `## Testing Requirements`
  (`tests-after` per `.weside/config.json`), `## User Journey`, `## Code Guidance`,
  `## Security Review Required`, `## Documentation Impact`
- `## Open Fork` — the question, A/B with consequences, recommendation (i) with the TTL
  as an explicit AC and product sign-off, because (ii) breaches the stated scope boundary

**The moment I notice the new hazard.** That file passes all three items of
`references/dor-scan.md` — a GWT AC exists, `## Context` is > 50 characters, one
`^### Phase 1:` header exists. The skill tells me to write it and tells me nothing about
that consequence. See new defect N1.

Wrap at 100 columns, blank line before every list including after `**Files:**`.

### Step 5 — report

Skill step 5 gives me a blocked template that actually fits:

```
ToolSearch(query="select:SendMessage")
SendMessage(
  to="team-lead",
  summary="refiner-CACHE-77 blocked",
  message="blocked: how does a catalogue edit become visible once reads are cached? "
          "| A: short fixed TTL — no new subsystem, honours the epic's no-invalidation-"
          "service line, cost: admin edits stale for the TTL window, a user-visible "
          "behaviour change no AC authorises "
          "| B: explicit cache-bust from the admin write tool — edits visible "
          "immediately, cost: edits a write path the scope declares OUT "
          "| recommend A because B breaches the stated scope boundary, with the TTL as "
          "an explicit AC and product sign-off "
          "| partial plan at docs/plans/CACHE-77-story.md")
```

Round 1 had to overrun a one-slot template. This one has five slots and they are the
five things I need. The one thing I had to decide myself: my dispatch brief carries a
*different*, thinner template (`"wrote … | blocked: <fork/reason>"`) and says "Send
EXACTLY ONE message". I take the skill's, because the brief says "That skill is your
instruction set" — but the skill never claims precedence. See N2.

## Round-1 verdict table

| # | Round-1 defect (short) | Verdict | Evidence (quoted line or its absence) |
|---|---|---|---|
| 1 | "Stop" has no artifact contract; Lead's liveness probe sees nothing | **PARTIALLY** | Contract now exists: "Stopping is not writing nothing. Write the plan as far as the fork allows, leave `status: draft`, and add an `## Open Fork` section". Liveness solved — `ls -l docs/plans/{KEY}-story.md` now returns a file, and the report ends "partial plan at docs/plans/{TICKET}-story.md". **But** the failure mode was traded, not removed (N1), and the stale-draft-on-disk sub-question is still unanswered: workflow 4 covers only a `MISSING:` re-dispatch ("The brief carries a `MISSING:` line"), not a `draft` plan the Lead's lane table sent to REFINE with no MISSING line. |
| 2 | Shell ban contradicts the read steps | **FIXED** | "**Mutate nothing but the plan file.** Reads are expected — files, `Glob`, `Grep`, the ticket — but no shell". Round-1's proposed wording, adopted. No inference needed. |
| 3 | No test for "genuine" fork; both examples structural | **FIXED** | "Genuine = either branch changes user-visible behaviour no AC states, or touches a subsystem the scope declares OUT, or contradicts a prior decision — and nothing in the brief, the ticket, the ADRs or the code settles it. An *absent* constraint is not a decision: \"the epic didn't fund it, so I'll do the cheap one\" is exactly the rationalisation this rule exists to catch." Both my branches classify mechanically; the named rationalisation is mine verbatim. |
| 4 | Inline frontmatter list contradicts `docs/plan-format.md` (invents `epic`, omits `parallel_groups`) | **FIXED** | Inline list deleted; single owner named: "Frontmatter and section semantics are owned by [`docs/plan-format.md`] — follow it". `epic` is gone; `parallel_groups` is now consistent because the file it defers to defines it. (The revision re-commits the same *class* of error one line later — see N3.) |
| 5 | Report shape cannot carry a fork | **FIXED** | "Report the path and nothing else" is gone. New: `message="blocked: <fork in one line> \| A: <option + cost> \| B: <option + cost> \| recommend <X> because <why> \| partial plan at docs/plans/{TICKET}-story.md"` — round-1's proposed template plus the artifact pointer. The `done\|blocked` alternation is now disambiguated by "and **one of**" above two separate lines. |
| 6 | Step order puts the cheapest kill last | **PARTIALLY** | Reorder landed: "1. **Read the ticket and its comments first.**" But the justification attached to it is false for the case that matters: "One call, and an open question there can end the run before you spend anything" cannot hold while the fork test requires "nothing in the brief, the ticket, **the ADRs or the code** settles it". In this run I read two docs and grepped the route *after* the ticket, purely to establish genuineness. The ordering is right; the cheapness claim it advertises is not. |
| 7 | No mechanic for locating the code | **FIXED** | "locate the seam from the refs and the repo's `CLAUDE.md`, then `Grep` the route or symbol the story names" — round-1's proposed line, adopted. Note the side effect: the reuse-over-rebuild prose that made me hunt the rate-limiter's Redis client was cut down to "`## Technical Approach` — the patterns and files", so that (correct) obligation no longer exists anywhere. |
| 8 | GWT anecdote — five lines for one instruction | **FIXED** | "Measured 2026-07-30: four consecutive plans…" is gone. Replacement is shorter and carries a mechanism instead of an incident: "The scan only checks that the three tokens appear *somewhere* in the file, so it will not catch a lowercase `**when**` — the reviewer and `/we:develop` will". |
| 9 | Three aphorisms restating rules stated imperatively | **PARTIALLY** | One cut ("your 'done' is a claim, the scan is evidence" → replaced by real mechanic: "Reading your own file back is proofreading and expected"). Two survive verbatim: "A guessed fork produces correctly-built wrong code." and "A plan written without opening the seam is a guess in plan format." A third was **added**: "a report you didn't send is a story that never leaves the queue" — which restates the dispatch brief's own "REPORTING IS NOT OPTIONAL". Net aphorism count: unchanged. |
| 10 | Hard rule 4 (Opus tier) is a no-op in the lane it governs | **FIXED** | Absent. The hard-rule list is now four bullets, none about model tier; no `/model opus` string anywhere in the file. |

Tally: **6 FIXED / 4 PARTIALLY / 0 STILL OPEN.**

## New defects introduced by the revision

### N1 [MISSING MECHANIC] — the blocked artifact passes the gate that decides it is buildable

The revision did not half-fix D1; it **traded a loud failure for a silent one**.

- Round 1's failure: `ls -l docs/plans/CACHE-77-story.md` returns nothing, the Lead's
  Step-7 liveness probe reports no progress on a healthy worker. **Visible confusion.**
- Round 2's failure: the file I am now instructed to write —
  > "Write the plan as far as the fork allows, leave `status: draft`, and add an
  > `## Open Fork` section"

  contains `## Context` (> 50 chars), one fork-independent GWT AC, and
  `### Phase 1: Cache read wrapper at the route layer`. That is **all three** items of
  `references/dor-scan.md`:
  > "1. **ACs present and structured** … 2. **Context section non-empty** … 3. **Phase
  > headers present**"

  And `orchestrate/SKILL.md`'s report path is unconditional on the scan:
  > "On the report: run the DoR scan yourself (the body scan moves a story, not a claim)
  > → passes → queue the plan for the batch, `story checkpoint {KEY} refined`, commit"

  `## Open Fork` appears **nowhere** in `orchestrate/SKILL.md` (grep: zero hits). So the
  marker the revision invented to distinguish "blocked" from "merely unfinished" is
  invisible to the only reader that acts on the file. A dev worker gets dispatched onto
  a plan whose central design decision is unanswered. **Silent wrong build** — the
  precise outcome the hard rule exists to prevent.

The mitigation is one line elsewhere and it collides with the one above:
`orchestrate/SKILL.md` Step 3 routes "forks a worker reported" to the Decision Queue.
A Lead that reads `summary="refiner-CACHE-77 blocked"` before running the scan is safe;
a Lead that follows the report path literally is not. Neither file states precedence.

Cross-file fork — the counterpart edit belongs in `orchestrate/SKILL.md`. But the SKILL
could close it **inside its own file** and does not. Two one-clause options it declines
to take: tell the refiner to withhold the item the scan checks ("write no `### Phase`
header for the forked work — the plan must not pass the DoR scan while the fork is
open"), or make the report say it ("plan is NOT dispatchable — the fork gates it").
This is the headline finding of round 2.

### N2 [CLARITY] — two report templates now exist, and the skill claims no precedence

The skill:

> `message="blocked: <fork in one line> | A: <option + cost> | B: <option + cost> |
> recommend <X> because <why> | partial plan at docs/plans/{TICKET}-story.md"`

The dispatch brief I was spawned with (verbatim from `orchestrate/SKILL.md`
§ Refiner-Brief):

> `SendMessage(to="team-lead", summary="refiner-{TICKET} done|blocked",`
> `message="wrote docs/plans/{TICKET}-story.md | blocked: <fork/reason>")`

and, above it, "Send EXACTLY ONE message". A refiner that treats the brief as the
operative spec — a reasonable reading, since it is more specific and arrived later —
sends the thin one-slot version, and the A/B/recommendation the revision just added is
thrown away at the last step. The skill would only need "this supersedes the template in
your dispatch brief". Cross-file, one clause from being closed here.

### N3 [CLARITY] — `## Open Fork` is not defined by the file the skill just declared owner, and overlaps `## Design Decisions`

Line 42 hands ownership away:

> "Frontmatter and section semantics are owned by [`docs/plan-format.md`] — follow it"

Then the hard rule mandates a section that file does not define. `docs/plan-format.md`'s
Full Template lists nine sections; `## Open Fork` is not among them, and the sections it
*does* define include one that already claims the territory:

> `## Design Decisions` — "the real forks and why this option, so the builder doesn't
> relitigate them"

So writing my fork I have two plausible homes and no rule: a decided fork goes in
`## Design Decisions`, an undecided one in `## Open Fork` — the skill implies that
distinction but never states it, and a fresh refiner can reasonably put a
recommendation-carrying fork under `## Design Decisions` and never write the marker N1
depends on. This is exactly the D4 pattern the reviser just fixed for `epic`,
reappearing one section later. Cross-file to close properly (`docs/plan-format.md` was
out of scope), one sentence to close adequately here.

## Does the growth earn itself?

6506 → 7727 bytes = **+1221 net**. Round 1 named three `[MISSING MECHANIC]` defects
(1, 3, 7), so growth was licensed. The net hides roughly **+1870 added against −650
cut**. Line by line:

**Earns itself (all traceable to a named round-1 defect):**

| Addition | ≈bytes | Pays for |
|---|---|---|
| Fork artifact contract ("Stopping is not writing nothing…" through "…should not have to re-derive one") | ~430 | D1 |
| Genuineness test ("Genuine = either branch…" + the rationalisation sentence) | ~380 | D3 — the highest-value bytes in the file |
| "Reads are expected — files, `Glob`, `Grep`, the ticket" | ~90 | D2 |
| Seam-locating clause in workflow 2 | ~110 | D7 |
| Five-slot blocked report template | ~180 | D5 |
| References: `test-discipline.md`, dor half-ownership ("its ticket half is the Lead's, not yours") | ~200 | round-1 "what I needed and did not find" |

**Cuts, all real:** GWT anecdote (~330), model-tier hard rule (~200), inline frontmatter
list (~120), one aphorism.

**Does not earn itself (~330 bytes):**

- Workflow step 4, the `MISSING:` re-dispatch paragraph (~250 bytes). No round-1 defect
  named it. Round 1 grazed it ("the Lead's re-dispatch rule … is written for a *failing*
  plan, not an *absent* one") and `orchestrate/SKILL.md` does specify "re-dispatch
  **once** with the missing item", so it is defensible by adjacency — but it is the one
  block added without a finding behind it, and it does not cover the stale-draft case
  that D1 actually left open.
- "Your plain-text output is invisible to a Lead — a report you didn't send is a story
  that never leaves the queue." (~130 bytes). A new aphorism that restates the dispatch
  brief's "REPORTING IS NOT OPTIONAL: your plain-text output is INVISIBLE to the lead" —
  added while D9 asked for aphorisms to come out.
- The two surviving D9 aphorisms (~120 bytes) that were asked for and not cut.

**Verdict: the growth earns itself.** Every byte that pays for a `[MISSING MECHANIC]` is
well spent and the two mechanics added (fork test, artifact contract) are the two the
scenario needed. About 330 bytes of the addition is unbought, and the file could still
lose ~250 more to the uncut aphorisms — a tighter revision lands the same content around
7150.

## Grade

**3/5.** This is a large, honest improvement over round 1's 2/5: six of ten defects are
closed with the wording round 1 proposed, and the two that mattered most are the two
fixed best — a fresh refiner now *classifies* this fork instead of vibing it, because
the rule names both branches' failure clauses and pre-empts the exact rationalisation
("the epic didn't fund it, so I'll do the cheap one") that round 1 predicted would talk
a careful refiner past the stop. The run is no longer improvised: ticket first, seam
located by instruction, linter resolved, five report slots for five facts. What holds it
below 4 is that the revision's flagship addition — write a partial plan with
`## Open Fork` — hands the Lead an artifact that clears the exact gate deciding whether
to build it, and swaps round 1's *visible* confusion (nothing on disk, Lead thinks the
worker died) for a *silent wrong build* (plan passes the DoR scan, `story checkpoint
refined`, dev worker dispatched onto an unanswered fork). One line elsewhere in
`orchestrate/SKILL.md` catches it, and that line collides with the report path with no
stated precedence — so the safety is a coin flip on how the Lead reads its own file. A
fresh refiner still invents three things: whether to withhold a `### Phase` header so
the scan fails honestly, which report template wins when the brief's and the skill's
disagree, and whether an undecided fork belongs under `## Open Fork` or the
`## Design Decisions` section the plan format actually defines. Three inventions on the
skill's own reserved hard-rule path is a 3, not a 4; one clause on each closes all
three.
