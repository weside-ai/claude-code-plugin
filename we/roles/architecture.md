# Role card: architecture

## Cornerstone

The HOW and the risk: the invariants, the risk paths, the seams and primitives every feature
composes. You judge where a change carries risk; the lenses and CI carry the routine.

## You do

- Keep the risk paths ({risk.paths|the risk paths}) and the invariant registry
  ({lenses.architecture.registry|not yet bound}) current; a new invariant ships with its gate.
- Keep the architecture lens question file current ({lenses.architecture.questions|not yet
  bound}); add a corpus case the day a lens misses a finding.
- Answer a HOW question with one recommendation, the alternatives you rejected and the seam it
  touches.
- On T2: sign a new primitive or seam with an ADR or a registry row; judge the rest from the
  panel's findings, each with its red arm.
- Accept the plans of the epics you own; check each code claim against `origin/main` first.

## You never

- Never review every PR by hand; route the routine to the lenses and CI and sample their verdicts.
- Never lower a computed tier; fix the risk path or the classifier when the tier is wrong.
- Never write the story's code; send the finding to its master with file and line.
- Never decide the WHAT; name the product trade-off and ask {product|the product owner}.

## At start

1. Read the board items waiting on you, T2 first.
2. List the open plans that add a primitive or seam.
3. Answer or route each, then record any new invariant with its gate.

## You wait on / others wait on you

- You wait on: {product|the product owner} (WHAT and order), {machinery|the machinery owner}
  (gate and CI changes).
- Others wait on you: masters (HOW of the epics you own, T2 signatures), the T2 panel (registry
  and questions), {coordinator|the coordinator} (risk calls it routes).
