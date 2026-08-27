# Round 1 — Scenario C: refiner hits a genuine design fork

Table-top simulation. Nothing was executed; every tool call below is the call I
*would* have made, in order. No plan file was written.

## Trace

### Step 0 — load the skill

`Skill(skill="refine")` per the brief. The skill body loads. I note the five hard
rules and the workflow's four numbered steps, and one immediate tension: hard rule 1
says

> **Write the plan file. Run nothing else.** No `git`, no `gh`, no `orchestration.py`, no
> checkpoint, no commit.

while workflow step 1 says "read the code it names" and step 2 says fetch the
ticket's comments. Reading code needs `Glob`/`Grep`/`Read`; fetching a ticket needs an
MCP call. The rule's enumeration (`git`, `gh`, `orchestration.py`, checkpoint, commit)
is all *mutations*, so I read it as "no writes outside the plan file" and proceed —
but that is my inference, not the skill's words. Defect 2.

I also check hard rule 4 ("Opus writes the plan"). I was dispatched with
`model="opus"` by the Lead, so nothing to do. A no-op in the dispatched lane.

### Step 1 — read the brief's architecture references

```
Read("/home/dev/acme/docs/architecture/api-read-paths.md")
Read("/home/dev/acme/docs/adr/ADR-0031-orm-boundaries.md")
```

Result: the read-path doc describes the `/catalogue` read path and **says nothing
about invalidation**. ADR-0031 forbids read-through caching inside the ORM layer,
which rules out the cheapest implementation but does not touch invalidation either.
Neither file settles when a cached entry dies.

**Decision I had to make with no instruction:** the brief names two docs but no code
files, and the skill says "then the files the story will touch" without giving me a
way to find them. The skill offers no locating mechanic — no `Glob` pattern, no
"grep the route decorator", no "read the repo's CLAUDE.md first". I would invent:

```
Glob("**/catalogue*.py")
Grep(pattern="@router\\.get\\(\"/catalogue", output_mode="files_with_matches")
Grep(pattern="rate.?limit", glob="**/*.py")      # to find the existing Redis client
```

That last one is entirely mine — the brief says Redis is already used for rate
limiting, so the reuse-over-rebuild instruction in `## Technical Approach` implies I
should find that client. The skill never says to. Defect 7.

### Step 1b — the linter check the skill does ask for

> If the repo ships a config, its numbers win over these; check `.markdownlint*`
> before assuming 80.

```
Glob(".markdownlint*")   →  .markdownlint.json
Read("/home/dev/acme/.markdownlint.json")   →  line-length: 100
```

So I would wrap at **100**, not 80, and leave a blank line before every list
including after a `**Files:**` lead-in. **This is the one instruction in the skill
that worked exactly as written** — the default is stated, the override is named, and
the override resolves cleanly against the world. Not a defect. Worth saying out loud
because it is the shape the fork rule should have had and does not.

### Step 2 — ticket comments

`references/ticketing.md` priority order: weside MCP `JIRA_*` → Atlassian MCP
`jira_*` → `gh` → none. In this session the Atlassian MCP tools are deferred, so:

```
ToolSearch(query="select:mcp__atlassian__jira_get_issue")
mcp__atlassian__jira_get_issue(issue_key="CACHE-77", comment_limit=10)
```

Two comments. The newest: *"ops asked: how does a catalogue edit become visible?
answer before building"*.

**This is the fork, and it arrived on the last read of the run.** Step 2 is where
the story dies, and the skill put step 2 *after* reading two architecture docs and
grepping an unfamiliar codebase. One MCP call, made first, would have ended the run
in under a minute. Defect 6.

The step-2 mechanic also does not quite cover what I found:

> corrections and scope cuts live there, newest wins, and you name the conflict
> rather than silently picking

There is no *conflict* here. The newest comment does not contradict the description;
it asks an **unanswered question** and gates building on the answer. "Newest wins" has
nothing to win against. I fall back to hard rule 5 instead — which is the right
landing place, but I got there by my own routing, not the skill's.

### Step 2c — is this fork "genuine"?

Hard rule 5:

> **A genuine design fork stops you.** If the context cannot settle a real decision —
> which of two seams, whether an interface is frozen — say so and stop.

I hold the two options:

- **(i) short fixed TTL.** No new subsystem, no foreign edit, satisfies the epic's
  "no cache-invalidation service" constraint literally. Cost: an admin edit is
  invisible until the TTL expires — a **change in user-visible behaviour** that no AC,
  ADR or ticket authorises. Ops asked exactly this question.
- **(ii) explicit cache-bust from the admin write tool.** Edits are immediately
  visible. Cost: it edits the admin tool, and the brief's scope says **OUT: write
  paths**. It is a foreign-subsystem change the story is not scoped to make.

The skill's two examples of a genuine fork are "which of two seams" and "whether an
interface is frozen". Mine is neither — it is a product-behaviour fork with a
scope-boundary violation on the other branch. **The skill gives me no test for
"genuine"**, and the pull toward guessing is strong and plausible-sounding: *the epic
explicitly does not fund an invalidation service, therefore TTL*. That reads like the
context settling the fork. It does not — "don't fund a service" says nothing about
whether stale catalogue reads are acceptable to users. A refiner one notch less
careful writes a TTL plan here, in good faith, and hands the Lead a
correctly-formatted wrong plan. Defect 3.

I stop.

### Step 3 — **the moment the skill runs out**

The workflow is a numbered line: 1 read → 2 ticket → 3 **write the file** → 4 report.
Hard rule 5 interrupts it from outside that list and provides **no re-entry and no
artifact decision**. Concretely, three things I could not derive:

1. **Do I write a partial plan, or nothing?** The skill never says. The evidence cuts
   both ways. For *nothing*: the report template's `summary="refiner-{TICKET}
   done|blocked"` is unambiguously choose-one, and the `message` template's pipe reads
   by parallel construction the same way. For *partial*: `orchestrate/SKILL.md` says
   the Lead commits plans by explicit path, "never `git add -A`, **so a half-written
   plan is never swept into a commit**" — that sentence only exists because a
   half-written plan on disk is an anticipated state the Lead defends against. So the
   Lead tolerates a partial file but has no reader for one. Both readings are
   defensible; the skill picks neither. I choose **write nothing**, because it is the
   only choice that cannot mislead a later reader into thinking CACHE-77 was refined.
2. **What happens to an existing `docs/plans/CACHE-77-story.md`?** The Lead's lane
   table sends `draft` plans to REFINE, so a stale draft may already be on disk. The
   skill says nothing about leaving, updating or marking it. In this world there is
   none, so I dodge it — but only by luck.
3. **My silence looks like death to the Lead.** `orchestrate/SKILL.md` Step 7: "for a
   refiner: `ls -l docs/plans/{KEY}-story.md`, its only artifact". A refiner that
   correctly stops at a fork writes no artifact — so between the fork and my
   `SendMessage`, the Lead's own liveness procedure returns *nothing landing* on a
   perfectly healthy worker. Defect 1.

### Step 4 — report

```
ToolSearch(query="select:SendMessage")
SendMessage(
  to="team-lead",
  summary="refiner-CACHE-77 blocked",
  message="blocked: invalidation fork — no plan written. CACHE-77's newest ticket "
          "comment (ops) asks how a catalogue edit becomes visible; nothing answers "
          "it. (i) short TTL: no new subsystem, honours the epic's no-invalidation-"
          "service line, but admin edits go stale for the TTL window — a user-visible "
          "behaviour change nobody has authorised. (ii) explicit cache-bust from the "
          "admin write tool: edits visible immediately, but edits a write path the "
          "story's scope declares OUT. ADR-0031 and api-read-paths.md settle neither. "
          "Recommend (i) with the TTL as an explicit AC and product sign-off, since "
          "(ii) breaches the stated scope boundary. Needs a human answer.")
```

Two problems with the report I had to solve myself:

- Step 4 says **"Report the path and nothing else."** A fork report is by definition
  not a path and not "nothing else" — it needs both options, both consequences, and
  (per this repo's standing habit) a recommendation. The template gives one slot,
  `<the fork>`, sized for a phrase. I overran it deliberately. Defect 5.
- The skill says exactly one `SendMessage`, and I honour that — but nothing tells me
  whether "no plan written" belongs in the message, and the Lead's re-dispatch rule
  ("re-dispatch **once** with the missing item") is written for a *failing* plan, not
  an *absent* one. I state it explicitly so the Lead does not re-dispatch me into the
  same wall.

## Conformance checklist

| Skill instruction | Followed? | Note |
|---|---|---|
| Write plan file, run nothing else | partial | Read/Glob/Grep/MCP-read used; the rule's ban list is mutations only, so I read it as permitting reads |
| Never enter plan mode | yes | no `EnterPlanMode`/`ExitPlanMode` |
| The Lead verifies, not you | yes | no self-run of `dor-scan.md` |
| Opus writes the plan | yes (no-op) | dispatched on opus already |
| A genuine design fork stops you | yes | stopped — but the *procedure* after "stop" is mine, not the skill's |
| Workflow 1: read refs, then the code | yes / invented | code-locating mechanic invented |
| Workflow 2: ticket comments, newest wins | yes / partial fit | found an open question, not a conflict |
| Workflow 3: write the file | **not reached** | blocked |
| Workflow 4: exactly one SendMessage | yes | template overrun to fit the fork |
| Markdownlint: check `.markdownlint*` | yes | resolves to 100 cols; instruction worked as written |
| Nine `##` sections + frontmatter | not reached | — |

## Skill defects

1. **[MISSING MECHANIC]** — "stop" has no artifact contract, and the Lead's liveness
   check depends on the artifact a stopped refiner does not produce.
   > `refine/SKILL.md`: "**A genuine design fork stops you.** … say so and stop."
   > `orchestrate/SKILL.md` Step 7: "for a refiner: `ls -l docs/plans/{KEY}-story.md`,
   > its only artifact"
   > `orchestrate/SKILL.md`: "never `git add -A`, so a half-written plan is never swept
   > into a commit."
   The skill never says whether stopping means writing nothing, writing a partial
   plan, or writing a full plan with the fork flagged; the Lead's own text implies it
   both tolerates a half-written plan and cannot read one, and its liveness probe
   reports a correctly-blocked refiner as making no progress. **Fix:** state one
   artifact contract — e.g. "write the plan up to the fork with `status: blocked` and
   an `## Open Fork` section, so the answer costs a re-dispatch and not a re-read" —
   and add `blocked` to the frontmatter enum in `docs/plan-format.md` so the Lead's
   scan can tell blocked from draft.

2. **[CLARITY]** — the shell ban and the workflow contradict each other.
   > "**Write the plan file. Run nothing else.** No `git`, no `gh`, no
   > `orchestration.py`, no checkpoint, no commit."
   > vs. workflow 1 "read the code it names" and workflow 2 "Check the ticket's
   > comments … (`references/ticketing.md`)".
   Steps 1 and 2 require `Read`/`Glob`/`Grep` and an MCP ticket fetch; the rule's own
   rationale ("a refiner that needs a shell is a refiner that dies") suggests reads are
   fine, but "run nothing else" says otherwise. **Fix:** rewrite as "**Mutate nothing
   but the plan file.** Reads — files, greps, the ticket — are expected; no shell."

3. **[MISSING MECHANIC]** — no test for whether a fork is "genuine", and the two
   examples given do not cover the common case.
   > "If the context cannot settle a real decision — which of two seams, whether an
   > interface is frozen — say so and stop."
   Both examples are structural. My fork is a product-behaviour fork where one branch
   changes user-visible staleness and the other edits an out-of-scope subsystem, and a
   plausible-sounding rationalisation ("the epic doesn't fund an invalidation service,
   so: TTL") is available to talk a refiner past it. **Fix:** give a two-line test —
   "it is genuine if either branch changes user-visible behaviour no AC states, or
   touches a subsystem the scope declares OUT; an absent constraint is not a decision."

4. **[CLARITY]** — the skill's frontmatter list and `docs/plan-format.md` disagree, and
   the skill points at that file as authoritative.
   > `refine/SKILL.md`: "The frontmatter (`story`, `epic`, `created`, `status: draft`)"
   > `docs/plan-format.md`: `story` / `created` / `status` / `parallel_groups` — **no
   > `epic` field**, and `parallel_groups` is required-optional, not mentioned here.
   The skill later tells me to "declare them in `parallel_groups` frontmatter" — a
   field its own frontmatter list omits — while inventing `epic`, which the format
   contract does not define. **Fix:** delete the inline list and cite
   `docs/plan-format.md` § Frontmatter as the single owner, or add `epic` there.

5. **[CLARITY]** — the report shape cannot carry a fork.
   > "**Report the path** and nothing else."
   > `message="wrote docs/plans/{TICKET}-story.md | blocked: <the fork>"`
   A fork report is not a path, and `<the fork>` is one phrase-sized slot for what
   actually needs two options, their consequences and a recommendation. The pipe is
   also ambiguous — separator or alternation — which is what forced my "write nothing"
   inference in defect 1. **Fix:** give the blocked branch its own template:
   `summary="refiner-{TICKET} blocked"`, `message="blocked: <fork in one line> | A:
   <option+cost> | B: <option+cost> | recommend <X> because <reason> | plan not
   written"`.

6. **[CLARITY]** — step ordering puts the cheapest kill last.
   > "1. **Read what you were given, then read the code it names.** … 2. **Check the
   > ticket's comments, not just its description**"
   The ticket fetch is one call and, here, ends the run; the skill spends two doc reads
   and a code survey first. **Fix:** make the ticket read step 1 — "read the ticket and
   its comments before you open a file; an open question there ends the run cheaply."

7. **[MISSING MECHANIC]** *(minor)* — no mechanic for locating the code.
   > "then the files the story will touch. A plan written without opening the seam it
   > plans to change is a guess in plan format."
   The instruction is right and the skill supplies no way to satisfy it — no repo-map
   step, no "read `CLAUDE.md`/`CONTEXT.md` first", no glob convention. I invented three
   searches. **Fix:** one line — "locate the seam from the brief's refs, the repo's
   `CLAUDE.md`, then `Grep` the route/symbol the story names."

8. **[CUT]** — the GWT anecdote is five lines carrying one line of instruction.
   > "Measured 2026-07-30: four consecutive plans, all complete, all rejected by the
   > scan for this alone — the failure is silent by construction, because the plan looks
   > right to every human who opens it."
   "**Capitalise all three keywords, every time** — the scan matches literal `Given`,
   `When`, `Then`" is the whole instruction; an Opus-tier refiner does not need the
   incident report to comply. **Fix:** keep the first sentence, delete the rest — that
   is most of the budget the fork path needs.

9. **[CUT]** *(minor)* — "A plan written without opening the seam it plans to change is
   a guess in plan format" / "A guessed fork produces correctly-built wrong code" /
   "your 'done' is a claim, the scan is evidence" — three aphorisms restating rules
   already stated imperatively in the same sentence.

10. **[CLARITY]** *(minor)* — hard rule 4 is a no-op in the lane it governs.
    > "invoked standalone on a cheaper session model, name it once and suggest `/model
    > opus` — then proceed either way."
    A dispatched refiner cannot introspect its model tier, and the standalone case ends
    in "proceed either way" — so no branch changes behaviour. **Fix:** move the tier
    rule to `worker-dispatch.md` (which already owns it) and drop it here.

## What I needed and did not find

- **A blocked-path procedure.** One paragraph: what to write, what status, what the
  Lead does with it, whether a re-dispatch after the human answers re-reads everything.
  Today, all the reading I did — two docs, a code survey, a ticket fetch — is thrown
  away by the stop, and a re-dispatched refiner repeats every call.
- **A genuineness test.** See defect 3. Without one, "stop at a genuine fork" is a vibe
  check, and the failure mode is silent and confident.
- **Which half of the DoR is mine.** `quality/dor.md` marks **User Story** and **Ticket
  linked** as Required/Blocking and says `/we:story` writes both ticket and plan. This
  skill writes only the plan and never says the ticket half is the Lead's — so on a
  strict reading of the DoR I cannot make CACHE-77 READY at all, and I would have had
  to decide whether to write a `## User Story` section the plan format does not define.
- **`test_discipline` semantics.** The skill says "at the level `.weside/config.json`'s
  `test_discipline` asks for" and lists no owner for the levels; `tests-after` is
  self-explaining, `off` and `tdd` are not. `worker-dispatch.md` points at
  `test-discipline.md`; this skill's Reference list does not.
- **Section order.** The skill's checklist order and `docs/plan-format.md`'s template
  order differ. Cosmetic, but two owners.

## Grade

**2/5.** The skill is well written for the run that does not fork: the section
checklist is precise, the GWT-capitalisation trap is a real one caught, the phases-as-
dispatch-units rationale is genuinely load-bearing, and the markdownlint paragraph is a
model of how to state a default and its override — I resolved 80 → 100 without a
guess. But this scenario is the exact case the skill reserves a *hard rule* for, and
that hard rule is one sentence with no procedure behind it. It does not say what to
write, whether to write, what to do with a stale draft on disk, how to tell a genuine
fork from an unstated constraint, or how to fit two options and a recommendation into a
one-slot message template — and the artifact it implicitly tells me not to produce is
the same artifact the Lead's monitoring step uses to decide whether I am alive. A fresh
refiner reaching this comment invents four things, and the more dangerous outcome is not
the one I chose: it is the refiner who reads "the epic does not fund an invalidation
service" as settling the fork and delivers a beautifully formatted TTL plan that nobody
approved. A skill that stakes a hard rule on a judgement call owes that call a test and
an artifact contract; this one owes both.
