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
    - apps/backend/app/companion/core/consciousness.py
    - apps/backend/app/companion/core/_context_composer.py

  five_components_map:
    # Each of the 5 components has a canonical home (one or more directories/files)
    CONSCIOUSNESS: [apps/backend/app/companion/core/]
    SENSES:        [apps/backend/app/senses/]
    BODY:          [apps/backend/app/companion/channels/, apps/backend/app/tools/]
    MEMORY:        [apps/backend/app/companion/core/memory.py, apps/backend/app/crud/memory.py]
    EXPERIENCE:    [apps/backend/app/services/evolution/]

  forbidden_outside_consciousness:
    # Patterns that may NOT appear in any file outside identity_construction_paths
    - "system_prompt ="
    - "personality ="
    - "self.identity ="
```

If this block is missing, the lens errors out with a helpful message — there is no useful default for what "personality" means in any given project.

## Method

Five sub-checks:

### PC-1 — Identity Construction Sites

```bash
grep -rn "system_prompt\|personality\|consciousness" <backend_root>
```

Verify every match is inside `identity_construction_paths` OR is a docstring/comment OR is a function-parameter (not assignment). Any assignment-style match (e.g., `system_prompt = "..."`, `self.personality = ...`) outside the configured paths is a finding.

**Severity rule:** assignment outside paths = MAJOR. Documentation-only mention = no finding.

### PC-2 — Five-Components Boundary

For each of the 5 components, verify:

1. The component's canonical home contains the bulk of its logic.
2. No code OUTSIDE the home redefines or duplicates the component's responsibilities.

Concretely, for CONSCIOUSNESS:

```bash
# Find all files importing or defining "consciousness"
grep -rln "from.*consciousness import\|class.*Consciousness\|class.*Identity" <backend_root>
```

Every match must be inside the CONSCIOUSNESS home paths. Matches outside = MAJOR (component-leak).

For BODY: are tools and channels the ONLY output paths? If a service-layer file calls a tool's send-method directly, BODY is leaking.

For MEMORY: distinct from CHECKPOINTER? MEMORY = long-term factual memory (preferences, history), CHECKPOINTER = LangGraph conversation state. Conflation = MAJOR.

### PC-3 — `forbidden_outside_consciousness` Patterns

For each pattern:

```bash
grep -rln "<pattern>" <backend_root> | grep -v "<identity_construction_paths joined with -e>"
```

Every match outside is a MAJOR finding. Whitelist allowed via inline `# noqa: personality-cohesion` comment.

### PC-4 — System-Prompt Construction Audit

Find every site where a system prompt is built:

```bash
grep -rn "SystemMessage(\|system_prompt\s*=\s*[\"f]" <backend_root>
```

Each must be in `identity_construction_paths`. Common offenders:
- Channel files that prepend a "this is from telegram" preamble
- Skill agents that build their own system prompt
- Tool-result sanitizers that inject role hints

If a non-consciousness file constructs a system prompt, the Companion has multiple personalities depending on the channel/skill — exact opposite of cohesion.

### PC-5 — MEMORY ≠ CHECKPOINTER Boundary

Verify the documented separation:

- `MEMORY` writes go through `crud/memory.py` only (re-using the `crud-layer` chokepoint).
- `CHECKPOINTER` writes go through `LangGraphCheckpointer` only (re-using the `langgraph-checkpointer` primitive).
- No file writes to BOTH `memories` and `checkpoint_*` tables in the same function.

```bash
# Find conflations
grep -rln "checkpoint_writes\|checkpoint_blobs" <backend_root> | xargs grep -l "from app.crud.memory"
```

Any file in the intersection is a MAJOR finding (boundary violation).

## Output Format

Each finding follows the standard severity-tagged template:

```markdown
### PC-MAJ-N — <one-line description>

**Severity:** MAJOR
**Lens:** personality-cohesion
**Sub-check:** PC-1 (Identity Construction Sites)
**Cite:** `apps/backend/app/skills/agents.py:142`

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
