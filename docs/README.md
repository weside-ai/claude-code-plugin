# Documentation

Welcome. Pick your entry point.

## I want to use the plugin

- **[Getting Started](getting-started.md)** — install, configure, ship your first story end-to-end. ~30 minutes.
- **[Workflow](workflow.md)** — the full pipeline diagram + every phase explained.
- **[Skill Reference](skills.md)** — what every `/we:*` skill does and when to use it.
- **[Troubleshooting](troubleshooting.md)** — when something doesn't go as planned.

## I want to understand the concepts

- **[Companion Framework](concepts/companion-framework.md)** — the `.weside/` directory, the bridge file, how skills consume the framework
- **[Roles](concepts/roles.md)** — the nine role-lenses councils convene
- **[Meetings](concepts/meetings.md)** — vision / saga / epic / story, when to use which
- **[Memory](concepts/memory.md)** — what session-scope vs. persistent memory unlocks

## I want to go deeper

- **[MCP Layer](mcp.md)** — the Model Context Protocol integration that connects to weside
- **[Upgrade Paths](upgrade-paths.md)** — the Maturity Model: L1 (assisted) → L4 (orchestrated)

## I want to contribute or extend

- **[../CLAUDE.md](../CLAUDE.md)** — developer guide for plugin contributors (strategy, conventions, cross-repo)
- **[../we/CLAUDE.md](../we/CLAUDE.md)** — plugin instructions (loaded by Claude Code when the plugin is active)

---

## Suggested reading orders

### For a developer just installing

1. [Getting Started](getting-started.md)
2. [Workflow](workflow.md) (skim the diagram)
3. Use the plugin for a week
4. Come back for [Skill Reference](skills.md) when you hit something specific

### For a Product Owner exploring Agentic PO

1. [agenticproductownership.com](https://agenticproductownership.com) (the philosophy)
2. [Workflow](workflow.md) (what the pipeline does)
3. [concepts/meetings.md](concepts/meetings.md) (vision/saga/epic/story)
4. [Getting Started](getting-started.md) (try it)

### For a team lead evaluating adoption

1. [Workflow](workflow.md)
2. [Upgrade Paths](upgrade-paths.md) (where this fits in your team's maturity)
3. [concepts/companion-framework.md](concepts/companion-framework.md) (what the framework costs to adopt)
4. [Getting Started](getting-started.md) (pilot with one repo)

### For a developer integrating with weside

1. [mcp.md](mcp.md) (MCP architecture + tools)
2. [concepts/companion-framework.md](concepts/companion-framework.md) (how the plugin consumes MCP)
3. [Upgrade Paths](upgrade-paths.md) (the value at each level)

---

## Without a weside account

Everything in this docs/ tree works **without** a weside.ai account. The plugin runs all 27 skills standalone. `/we:onboarding` builds the full council from scratch even with no account — every role fills with a generic role-lens. (With an account, each role-lens is generic *or* weside-backed; a mixed council is normal.) Meetings at four Plan altitudes (Vision/Saga/Epic/Story). The pipeline ships stories end-to-end.

Where weside adds something, the relevant doc explicitly calls out *what's available standalone* and *what unlocks with an account*. No surprises; no lock-in.

If you're curious about the platform behind the plugin: [weside.ai](https://weside.ai) — where humans and AI meet as equals.
