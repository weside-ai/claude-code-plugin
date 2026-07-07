# Ticketing Detection

Detect the available ticketing tool in priority order:

1. **weside MCP** (`JIRA_*` Composio tools via `execute_tool`) → Jira (preferred)
2. **Atlassian MCP** (`jira_*` tools) → Jira (fallback)
3. **`gh` CLI** → GitHub Issues
4. **None** → Plan-only mode (no ticket, just `docs/plans/`)

Skills use generic actions ("Create ticket", "Move to In Progress") — never tool-specific API calls. Claude maps the generic action to the best available tool.

Ticket **content** rules (behavioural contracts, testable ACs, no file paths/line numbers) are owned by `ticket-briefs.md`.

**How Composio Jira works (path 1):** tools are called via `execute_tool(name="JIRA_CREATE_ISSUE", arguments='{...}')`. Tool names use the uppercase `JIRA_` prefix. Schemas are self-describing — use `get_tool_schema(name="JIRA_...")` to inspect parameters.

**Ticket transition (any skill that moves a ticket):** find the matching transition (names vary: "In Progress", "Start Progress", "In Bearbeitung"), execute it, then **verify** the ticket actually moved (re-fetch status) and retry once with a different transition name if not. Soft-fail loud (log a warning, continue) only when the workflow/permissions genuinely reject the move. GitHub Issues (no status transitions) / no ticketing tool → skip silently.

**If weside MCP is connected but Jira tools are missing**, tell the user:

> "Jira is not connected via your weside Companion. To enable it: weside.ai → Integrations → connect Jira, then activate it for your Companion."
