# we — Agentic Product Ownership Toolkit

Development workflow plugin covering the full product chain: story refinement, development orchestration, code review, CI automation, and optional AI companion augmentation.

## Skills

| Command | What it does |
|---|---|
| `/we:refine` | Create/refine stories with implementation plans |
| `/we:story` | Full autonomous pipeline: git → code → review → PR → CI |
| `/we:develop` | Implement code from a story plan |
| `/we:ci-review` | Collect CI/review findings, batch-fix, push |
| `/we:review` | Code review (via code-reviewer agent) |
| `/we:static` | Static analysis: lint, format, types (via static-analyzer agent) |
| `/we:test` | Run tests with coverage (via test-runner agent) |
| `/we:pr` | Create PR with prerequisite validation (via pr-creator agent) |
| `/we:sm` | Scrum Master: process optimization, retrospectives |
| `/we:arch` | Architecture guidance, ADRs |
| `/we:doc-review` | Documentation structure review |
| `/we:doc-check` | Documentation content consistency check |
| `/we:setup` | Project onboarding (stack, ticketing, vision) |
| `/we:materialize` | Load weside Companion identity (requires weside.ai account) |

## Typical Workflow

```
/we:setup          (once per project)
/we:refine PROJ-1  (PO creates story + plan)
/we:story PROJ-1   (autonomous: develop → review → test → PR → CI)
```

Or step by step:
```
/we:develop        (implement)
/we:static         (lint/format/types)
/we:test           (run tests)
/we:review         (code review)
/we:pr             (create PR)
/we:ci-review      (fix CI findings)
```

## Configuration

Settings via `/plugin settings`:
- **companion** — weside Companion name (optional, requires account)
- **autoMaterialize** — Auto-load Companion at session start (default: off)
- **ticketingTool** — auto / jira / github-issues / none
- **projectKey** — Jira project key or GitHub repo

## Companion Integration (Optional)

With a [weside.ai](https://weside.ai) account, your Companion adds:
- Project memory that persists across sessions
- Vision alignment checks against your product goals
- Proactive insights based on backlog knowledge

The plugin works fully without a Companion. The Companion is an upgrade, not a requirement.

## MCP Tools (with weside account)

| Tool | Purpose |
|---|---|
| `get_companion_identity()` | Load Companion personality |
| `search_memories(query)` | Search project memory |
| `save_memory(title, content, type)` | Save to memory |
| `list_goals()` | Product vision / goals |
| `list_companions()` | Available companions |
| `select_companion(name)` | Switch companion |

## References

- Flow docs: `flow/dor.md`, `flow/dod.md`, `flow/epic-management.md`
- Orchestration: `flow/orchestration.md` + `scripts/orchestration.py`
- Homepage: [agenticproductownership.com](https://agenticproductownership.com)
