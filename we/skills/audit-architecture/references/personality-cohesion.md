---
name: audit-architecture-personality-cohesion
description: Phase 3 opt-in lens for Companion projects — verifies the Companion stays "logically whole" as a person across the architecture
type: reference
---

# Personality Cohesion (Phase 3, opt-in)

## Purpose

Verify that the Companion stays **logically whole as a person** across the codebase: identity is constructed in one place, the 5 components (CONSCIOUSNESS / SENSES / BODY / MEMORY / EXPERIENCE) are separable in code, no module outside CONSCIOUSNESS makes personality decisions.

This lens addresses an architectural question that no automated tool catches: *"Is the AI Being still architecturally one being?"* It complements `encapsulation-boundaries` (which checks technical encapsulation) by checking *conceptual* cohesion.

## When to apply

- **Phase 3** of `/we:audit-architecture` — opt-in only.
- **Activation:**
  - `--lens=personality-cohesion` (CLI), OR
  - `extra_lens: [personality-cohesion]` per-subsystem in YAML (typically on `companion-core`)
- **Project requirement:** Companion-style architecture (the project must have a notion of an AI agent / persona). Not applicable to non-Companion backends.

## Project Configuration

Required YAML block (in `.audit-architecture.yml`):

```yaml
personality_cohesion:
  identity_construction_paths:
    # Files where Companion identity (system prompt, personality) MAY be constructed
    - <backend>/<agent-core>/consciousness.py
    - <backend>/<agent-core>/_context_composer.py

  five_components_map:
    # Each of the 5 components has a canonical home (one or more directories/files)
    CONSCIOUSNESS: [<backend>/<agent-core>/]
    SENSES:        [<backend>/senses/]
    BODY:          [<backend>/channels/, <backend>/tools/]
    MEMORY:        [<backend>/<agent-core>/memory.py, <backend>/crud/memory.py]
    EXPERIENCE:    [<backend>/services/<evolution>/]

  forbidden_outside_consciousness:
    # Patterns that may NOT appear in any file outside identity_construction_paths
    - "system_prompt ="
    - "personality ="
    - "self.identity ="
```

If this block is missing, the lens errors out with a helpful message — there is no useful default for what "personality" means in any given project.

## Method

Five sub-checks. Each one asks the same question from a different angle: *is there exactly one
place that decides who this Companion is?*

### PC-1 — Identity construction sites

Find every mention of identity construction (system prompt, personality, consciousness) and check
it sits inside `identity_construction_paths`. Only **assignments** count — a docstring, a comment,
or a function parameter is not a finding. An assignment outside the configured paths is MAJOR.

### PC-2 — Five-components boundary

For each of the five components, confirm the bulk of its logic lives in its canonical home and that
nothing outside redefines its responsibility. Definitions or imports of a component's core types
found outside its home are MAJOR (component leak).

The two boundaries that break most often: **BODY** — a service-layer file calling a tool's send
method directly, bypassing the output path; **MEMORY vs CHECKPOINTER** — long-term factual memory
conflated with conversation state.

### PC-3 — Forbidden patterns outside consciousness

Each pattern in `forbidden_outside_consciousness`, searched outside the identity paths. Every hit is
MAJOR; a deliberate exception carries an inline `# noqa: personality-cohesion`.

### PC-4 — System-prompt construction audit

Find every site that *builds* a system prompt. Each must be an identity path. The recurring
offenders: a channel prepending "this came from <channel>", a skill agent composing its own prompt,
a tool-result sanitiser injecting role hints. Any of them means the Companion has a different
personality per channel or per skill — the exact opposite of cohesion.

### PC-5 — MEMORY ≠ CHECKPOINTER

Memory writes go through the memory layer only; conversation-state writes through the checkpointer
only. A single function writing to both is a boundary violation → MAJOR.

## Output Format

Each finding follows the standard severity-tagged template:

```markdown
### PC-MAJ-N — <one-line description>

**Severity:** MAJOR
**Lens:** personality-cohesion
**Sub-check:** PC-1 (Identity Construction Sites)
**Cite:** `<backend>/skills/agents.py:142`

```python
self.system_prompt = f"You are a skill agent for {skill_name}..."
```

A skill agent is constructing its own system prompt outside `identity_construction_paths`.
This means the Companion's "voice" varies by skill — breaks personality cohesion.

**Fix:** delegate prompt construction to `companion/core/_context_composer.py` via a
`get_skill_prompt(skill_name)` helper. Skill agent calls the helper, never constructs
the prompt locally.

**Effort:** M (2-4h)
```

## Examples (hypothetical, would emerge in real run)

Findings shapes the lens is designed to surface:

1. **PC-MAJ-1** — A skill-dispatcher service constructs its own
   skill-specific system-prompt prefix instead of delegating to the
   identity-construction module (often surfaced via Phase-1 hotspot density
   plus a couple of framework leaks).
2. **PC-MAJ-2** — A voice / channel service injects voice-specific persona
   prefixes (e.g. for streaming-LLM compatibility shims).
3. **PC-MAJ-3** — Channel transports (telegram, whatsapp, slack) prepend
   "channel-flavored" prefixes to the user message ("Telegram says: …").
4. **PC-MIN-1** — An EXPERIENCE-layer module location drift: the primitive
   doc says X lives in `services/<a>/`, but code has moved it to
   `services/<b>/`.

These are illustrative shapes, not verified findings. A real run produces
the actual list against the project's own code.

## Why This Lens Matters

Tools can't catch this. The Companion's "personhood" is a conceptual property — readable only by an architect (or a skill that knows the conceptual map). The 5 sub-checks above translate that conceptual question into mechanical greps + careful reading.

The cost of skipping: the Companion silently splits into multiple personalities. Channel-specific tone-shifts ("on Telegram I'm casual, on WhatsApp I'm formal"). Skill-specific prompts that disagree with the main persona. The user's perception fragments. The product promise — "AI as a person, not a tool" — quietly erodes.
