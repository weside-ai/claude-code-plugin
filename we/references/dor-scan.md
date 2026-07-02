---
name: dor-scan-reference
description: The 3-item plan-completeness scan (GWT ACs, Context, Phase headers). Single owner — referenced by /we:build, /we:develop, /we:orchestrate, /we:story. Loaded on demand.
---

# DoR Scan (3-item plan-completeness check)

The minimal machine-checkable gate that a Story plan (`docs/plans/{TICKET}-story.md`) was
actually refined. It is the shared subset of the full DoR (`quality/dor.md`) that skills
verify before executing or dispatching a plan.

Check all three:

1. **ACs present and structured:** the plan contains at least one occurrence of `Given` AND
   `When` AND `Then` (GWT acceptance-criteria tokens). A plan with no GWT ACs hasn't been
   accepted as DoR-complete.
2. **Context section non-empty:** the plan has a Context section with > 50 characters of
   actual content (not just a header).
3. **Phase headers present:** at least one `### Phase \d+:` header exists
   (regex: `^### Phase [0-9]+:`).

**On failure:** stop, name the specific missing item(s), and point to `/we:story {TICKET}`
to complete the plan. Do NOT proceed with an incomplete plan.

This is the same scan `orchestration.py`'s ready-set computation applies
(`_body_is_refined`) — the wording here and the code must not drift.
