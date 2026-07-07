# Design Vocabulary

The shared language for designing and cutting code. Use these terms exactly — consistent
language is the whole point. A leading word recruits priors the model already holds; it only
works when every skill uses the same one.

Consumers: `/we:story` (plan authoring), `/we:develop`, `/we:diagnose`,
`/we:audit-architecture` (deepening lens), the `code-reviewer` agent, `/we:meet` (story cuts).

## Terms

**Seam** *(Michael Feathers)* — a place where you can alter behaviour without editing in that
place; the location where a module's interface lives, and therefore the surface tests cross.
Where the seam goes is its own design decision, distinct from what sits behind it.
*Avoid:* boundary (overloaded with DDD's bounded context).

**Tracer bullet** — a vertical slice that runs end-to-end through every layer, shipped one at
a time. Each tracer bullet responds to what the last one taught you. The opposite of
layer-by-layer work, where nothing is provable until everything is done.
*Avoid:* vertical slice (say tracer bullet), phase, layer.

**Deep module** — a lot of behaviour behind a small interface at a clean seam. **Shallow
module** — an interface nearly as complex as the implementation it fronts (a pass-through).
Depth is a property of the interface, not the implementation: a deep module may be composed
of small parts internally — they just aren't part of the interface.
*Avoid:* component, service, "well-abstracted".

**Deletion test** — imagine deleting the module. If complexity vanishes, it was a
pass-through. If complexity reappears across N callers, it was earning its keep. The fastest
way to tell deep from shallow.

**Tight** *(of a feedback loop)* — fast, deterministic, low-overhead, and agent-runnable in
one command. A 30-second flaky loop is barely better than no loop; a 2-second deterministic
one is a debugging superpower.
*Avoid:* "fast feedback", "quick iteration".

## Principles

- **The interface is the test surface.** Callers and tests cross the same seam. Wanting to
  test *past* the interface means the module is probably the wrong shape.
- **One adapter means a hypothetical seam; two adapters means a real one.** Don't introduce
  a seam unless something actually varies across it.
- **Accept dependencies, don't create them.** A function that constructs its own gateway
  can't be tested through its seam; one that receives it can.

---

*Adapted from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT).*
