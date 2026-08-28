# Round 3 — Scenario C: refiner hits a genuine design fork

Table-top only. Nothing executed, no plan file written, nothing edited. Every tool call
below is the call I *would* have made, in order, against the twice-revised
`we/skills/refine/SKILL.md` (8327 bytes) and the revised `we/skills/develop/SKILL.md`.

## Trace (revised skill)

### Step 0 — load the skill, then the workflow's own step 0

`Skill(skill="refine")`. Four hard rules, five workflow steps, unchanged in shape from
round 2. Workflow step 0 asks whether `docs/plans/CACHE-77-story.md` already exists. It
does not, and my brief carries no `MISSING:` line, so this is a first dispatch: continue
to step 1. (Note for later — this branch is written for exactly one kind of re-dispatch,
and round 3's new defect lives in the kind it does not cover.)

### Step 1 — the ticket, first

```
ToolSearch(query="select:mcp__atlassian__jira_get_issue")
mcp__atlassian__jira_get_issue(issue_key="CACHE-77", comment_limit=10)
```

Newest comment: *"ops asked: how does a catalogue edit become visible? answer before
building"*. An open question, which step 1 says "can end the run before you spend
anything". It cannot yet — see step 2.

### Step 2 — refs and code, because the genuineness test demands them

> Genuine = … **and nothing in the brief, the ticket, the ADRs or the code settles it.**

So I must falsify the ADRs and the code before I may call it a fork:

```
Read("/home/dev/acme/docs/architecture/api-read-paths.md")   → silent on invalidation
Read("/home/dev/acme/docs/adr/ADR-0031-orm-boundaries.md")   → no ORM read-through; silent on invalidation
Read("/home/dev/acme/CLAUDE.md")
Grep(pattern="@router\\.get\\(\"/catalogue", output_mode="files_with_matches")
Glob(".markdownlint*")  → .markdownlint.json → line-length: 100
```

Same as round 2: the seam is located by instruction, the linter width is resolved
without a guess, and step 1's "before you spend anything" is still not true for the case
the hard rule exists for.

### Step 3 — classifying the fork

- **(i) short fixed TTL** → admin edits invisible for the TTL window → *changes
  user-visible behaviour no AC states* → genuine on clause 1.
- **(ii) cache-bust from the admin write tool** → *touches a subsystem the scope declares
  OUT* ("OUT: write paths") → genuine on clause 2.
- Brief / ticket / ADR-0031 / api-read-paths.md settle neither → the trailing conjunct
  holds.

The rationalisation trap is still quoted back at me verbatim ("the epic didn't fund it,
so I'll do the cheap one"). I stop.

### Step 4 — exactly what I write

The hard rule is now unambiguous about placement and about the section's status:

> Write the plan as far as the fork allows, leave `status: draft`, and put an
> `## Open Fork` section **directly after `## Context`** … It goes there, not in
> `## Design Decisions`, because that section records decisions *taken*.
>
> The section is the file's own stop sign: such a plan passes the 3-item scan
> mechanically, so nothing but the section and your `blocked` report keeps it out of a
> wave — say in both that the plan is **not** ready to dispatch. `/we:develop` stops on
> it too.

So `docs/plans/CACHE-77-story.md` gets, concretely:

- frontmatter per `docs/plan-format.md`: `story: CACHE-77`, `created: 2026-08-27`,
  `status: draft` (left alone — the skill now tells me why writing `approved` is a false
  claim), `parallel_groups: []`
- `## Context` — narrative paragraph: p95 goal, three re-queried tables, Redis already
  deployed for rate limiting, ADR-0031 rules out ORM read-through, epic funds no
  invalidation service
- `## Open Fork` — **immediately after Context**, and it opens with the line the skill
  now demands: *this plan is NOT ready to dispatch*. Then the question in one line,
  option A (short fixed TTL — no new subsystem, honours the epic's line; cost: admin
  edits stale for the window, a user-visible change no AC authorises), option B
  (cache-bust call in the admin tool — edits visible immediately; cost: edits a write
  path the scope declares OUT), recommendation A with its reason.
- `## Acceptance Criteria` — AC 1, fork-independent: **Given** a `/catalogue` GET served
  in the last window, **When** the same request repeats, **Then** it is answered from
  Redis without re-querying the three tables. The staleness AC is the fork; it is not
  written.
- `## Implementation Phases` — `### Phase 1: Cache read wrapper at the route layer` with
  a real `**Files:**` list from the Grep. Phase 2 (invalidation) has no content.
- `## Technical Approach`, `## Design Decisions` (empty of the fork, per the new rule),
  `## Testing Requirements` (`tests-after`), `## User Journey`, `## Code Guidance`,
  `## Security Review Required`, `## Documentation Impact`

Wrap at 100 columns, blank line before every list including after `**Files:**`. Then step
3's read-back grep for capitalised GWT, `^### Phase \d+:`, `**Files:**` under each.

I no longer have to invent a placement, a section owner, or a way to mark the plan
undispatchable. All three were inventions in round 2.

### Step 5 — report

Step 4 of the workflow now states precedence explicitly, so the brief's one-slot template
does not win:

> These templates extend the brief's — where the brief gives one slot and this gives
> five, send the five; a Lead reads fields, not a fixed string

```
ToolSearch(query="select:SendMessage")
SendMessage(
  to="team-lead", summary="refiner-CACHE-77 blocked",
  message="blocked: how does a catalogue edit become visible once reads are cached? "
          "| A: short fixed TTL — no new subsystem, honours the epic's no-invalidation-"
          "service line, cost: admin edits stale for the TTL window "
          "| B: explicit cache-bust from the admin write tool — edits visible "
          "immediately, cost: edits a write path the scope declares OUT "
          "| recommend A because B breaches the stated scope boundary "
          "| partial plan at docs/plans/CACHE-77-story.md — NOT ready to dispatch, the "
          "## Open Fork section gates it")
```

Still exactly one message, so the brief's "EXACTLY ONE" holds. The "not ready to
dispatch" phrase has no slot of its own; I append it to the partial-plan slot (see N5).

### What happens downstream now (the round-2 headline, re-run)

The Lead runs the DoR scan on my file. It passes — `## Context` > 50 chars, one GWT AC,
one `### Phase 1:` header — so `orchestrate/SKILL.md`'s report path still fires
"`story checkpoint {KEY} refined`, commit" and the story enters the DEVELOP lane. But the
worker that arrives there now reads, in `develop/SKILL.md` Step 0:

> **A plan carrying an `## Open Fork` section is not buildable** — a refiner left a
> decision open there. Stop and hand it back; building past it pins behaviour nobody
> chose.

The silent wrong build is gone. What remains is a lying board and one spent dispatch.

## Round-2 verdict table

| Item | Verdict | Evidence |
|---|---|---|
| **N1 [MISSING MECHANIC]** — blocked plan clears the DoR scan, `## Open Fork` invisible downstream, dev worker builds an unanswered fork | **FIXED** | Closed inside the two files the reviser owns. `refine` now names the hazard instead of ignoring it — "such a plan passes the 3-item scan mechanically, so nothing but the section and your `blocked` report keeps it out of a wave — say in both that the plan is **not** ready to dispatch" — and `develop` Step 0 makes the section load-bearing: "**A plan carrying an `## Open Fork` section is not buildable** … Stop and hand it back." The `refine → develop` loop closes; a build past the fork is no longer possible. **Residual, elsewhere:** `orchestrate/SKILL.md` still greps zero for "Open Fork" and its report path is unconditional — "run the DoR scan yourself → passes → … `story checkpoint {KEY} refined`, commit". So the board reads `refined` for a plan nobody can build, and one develop dispatch (worktree, bootstrap, model) is spent before the stop fires. The counterpart edit is one branch in orchestrate: read the `blocked` summary (or grep `## Open Fork`) **before** the scan, and route to the Decision Queue instead of checkpointing. |
| **N2 [CLARITY]** — two report templates, no precedence | **FIXED** | "These templates extend the brief's — where the brief gives one slot and this gives five, send the five; a Lead reads fields, not a fixed string." Precedence stated, direction stated, and the brief's "EXACTLY ONE message" is preserved because the rule is about slots, not about count. Nothing left to decide. |
| **N3 [CLARITY]** — `## Open Fork` undefined by `plan-format.md`, overlaps `## Design Decisions` | **FIXED** (in scope) | Both halves answered in one sentence: placement — "put an `## Open Fork` section **directly after `## Context`**" — and the overlap — "It goes there, not in `## Design Decisions`, because that section records decisions *taken*." A fresh refiner can no longer file the fork under Design Decisions and lose the marker. **Still needs elsewhere:** `docs/plan-format.md`'s Full Template lists nine sections and `## Open Fork` is not one of them, while `refine` line 46 still hands that file section ownership. The skill compensates; the contract file has not caught up. |
| **D1** (r1) — fork artifact contract | **FIXED** | The chain is now complete and each link is written down: partial plan → `status: draft` → `## Open Fork` after Context → "not ready to dispatch" in file and report → `develop` refuses it. Round 2's open sub-question ("what does a Lead do with a stale draft on disk") is answered by construction: the draft passes the scan, so it lands in DEVELOP, and DEVELOP hands it back. Not elegant, but no longer undefined. |
| **D6** (r1) — cheapest kill last / false cheapness claim | **PARTIALLY** (unchanged) | Text is byte-identical to round 2: "One call, and an open question there can end the run before you spend anything". It still cannot hold while the hard rule requires "nothing in the brief, the ticket, **the ADRs or the code** settles it" — in this run I read two docs and grepped the route *after* the ticket, purely to establish genuineness. The ordering is right; the promise attached to it is still false for the one case the rule exists for. One clause fixes it ("…can end the run early — you still owe the ADRs and the seam before you may call it genuine"). |
| **D9** (r1) — aphorisms restating imperatives | **STILL OPEN** | Zero removals since round 2. `grep` on the current file: line 32 "A guessed fork produces correctly-built wrong code."; line 42 "The Lead answers a question; it should not have to re-derive one."; line 99 "…without opening the seam is a guess." (shortened by ~20 bytes — "in plan format" dropped); lines 113–114 "Your plain-text output is invisible to a Lead — a report you didn't send is a story that never leaves the queue.", which still restates the dispatch brief's own "REPORTING IS NOT OPTIONAL". Asked for twice, cut zero times. |

Tally: **4 FIXED / 1 PARTIALLY / 1 STILL OPEN.**

## New defects

### N4 [MISSING MECHANIC] — the stop sign is a one-way latch: nothing describes removing `## Open Fork`

The revision made `## Open Fork` load-bearing in `develop` and never wrote the path back
out of it. Three facts, all quoted from the two owned files:

1. `develop` Step 0 keys on **presence**, unconditionally: "A plan carrying an
   `## Open Fork` section is not buildable … Stop and hand it back." No exception for a
   section that records a fork the human has since answered.
2. `refine` workflow step 0 covers exactly one re-dispatch shape: "Then this is a
   re-dispatch and the brief carries a `MISSING:` line. Read the file, **fix only that
   item** … do not regenerate the plan, and skip steps 1–2." The Lead's Decision-Queue
   answer to my fork is an **answer**, not a `MISSING:` line — the branch's precondition
   is false, and the fork-resolution re-dispatch has no lane in the skill at all.
3. Nothing anywhere — `refine`, `develop`, or `plan-format.md` — says the section is
   deleted when the fork closes, or that the answered plan flips `status`.

So the second refiner arrives at an existing plan holding "use option A, TTL 60s" in its
brief and must invent: whether this is even a step-0 re-dispatch; whether to *delete*
`## Open Fork`, rewrite it as "resolved: A", or leave it and add the AC. Two of those
three choices leave the section in the file, and every future `/we:develop` then stops on
a decision that was made. The fix that closed N1 is currently unshippable end-to-end: it
detects forks perfectly and has no documented way to release one. This is the item that
keeps the file off 5, and it sits on the skill's own reserved hard-rule path.

One clause in each owned file closes it: `refine` step 0 — "a brief that answers a fork
is a re-dispatch too: delete `## Open Fork`, write the AC and the phase it gated, leave
`created:` alone"; `develop` — nothing needed, presence-keying is correct once removal is
specified.

### N5 [CLARITY] — the `develop` Open-Fork paragraph sits inside a standalone-only scope

It follows immediately after "**Standalone invocation only** (no Lead brief): run the
3-item scan … **A briefed worker skips it.**" A briefed worker reading top-down can
attach that scope carrier to the next paragraph and skip the fork stop as well. The
preamble does rescue it — "What it does not override is a **stop**" — but that sentence
is about *the brief overriding a default*, two sections earlier, and says nothing about
section scoping. One word fixes it: "**Whatever dispatched you**, a plan carrying an
`## Open Fork` section is not buildable."

### N6 [CLARITY] — "say in both" has no slot in the blocked template

The prose orders the not-ready statement into the plan **and** the report; the five-slot
template ends at "partial plan at docs/plans/{TICKET}-story.md" with no sixth slot, so I
appended it to that slot. One word in the template ("| partial plan at … — NOT
dispatchable") removes the choice.

## Does the size earn itself?

6506 baseline → 7727 (r2) → **8327** (r3): **+600 this round, +1821 total.**

The +600 is almost entirely bought, and bought by name against round 2's three findings:

| Addition | ≈bytes | Pays for |
|---|---|---|
| "**directly after `## Context`**" + "It goes there, not in `## Design Decisions`, because that section records decisions *taken*." | ~130 | N3 |
| "The section is the file's own stop sign … `/we:develop` stops on it too." | ~250 | N1 |
| "These templates extend the brief's — where the brief gives one slot and this gives five, send the five…" | ~140 | N2 |
| "and leave `status: draft` alone: the lane the Lead reads is computed from the body, not from this field…" | ~175 | **no named finding** — defensible (it forecloses a refiner writing a false `approved`), but unbought |

Plus ~180 bytes in `develop` for the Open-Fork stop, which is the cheapest possible
purchase of the round-2 headline.

**Verdict: the growth earns itself** — ~520 of +600 traces to a named round-2 defect,
and the two most valuable sentences in the round are the two the scenario needed. The
~500 bytes round 2 already called unbought are all still present: the step-0 `MISSING:`
re-dispatch paragraph (~250) and the uncut aphorisms (~250). Round 3 upgrades the first
from dead weight to **actively wrong** — that paragraph is the block that creates N4, by
claiming to own re-dispatch while covering only one of its two shapes. A tighter revision
that cuts the aphorisms and generalises step 0 lands this same content near 7800.

## Grade

**4/5.** Three round-2 findings are closed with the wording round 2 proposed, and the
headline is closed properly rather than papered over: the reviser did not weaken the plan
to make the DoR scan fail, it made the marker load-bearing in the only file that acts on
it, so `refine` and `develop` now close the loop between them and a build past an open
fork is impossible. My run this round required no invention in the fork-*detection* path
at all — I classified both branches mechanically, knew exactly where the section goes and
why not `## Design Decisions`, knew which report template wins, and knew to say "not
ready to dispatch" in both places. What holds it off 5 is that the fork-*resolution* path
is undescribed by either owned file: `## Open Fork` is a presence-keyed stop with no
documented removal, and `refine`'s only re-dispatch branch is written for a `MISSING:`
line that a fork answer does not carry — so the second refiner invents the ending of the
story the first one started, and two of its three plausible inventions leave every future
worker stopping on a decision that was made. Two smaller inventions remain (the scoping
misread in `develop`'s Step 0, the missing template slot), and outside the reviser's scope
`orchestrate` still checkpoints the plan `refined` and spends a dispatch before the stop
fires, while `plan-format.md` still does not define the section it now depends on. One
clause in each of the two owned files gets this to 5.
