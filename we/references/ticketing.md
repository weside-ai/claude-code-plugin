# Ticketing Detection

Detect the available ticketing tool in priority order:

1. **weside MCP** (`JIRA_*` Composio tools via `execute_tool`) → Jira (preferred)
2. **Atlassian MCP** (`jira_*` tools) → Jira (fallback)
3. **`gh` CLI** → GitHub Issues
4. **None** → Plan-only mode (no ticket, just `docs/plans/`)

Skills use generic actions ("Create ticket", "Move to In Progress") — never tool-specific API calls. Claude maps the generic action to the best available tool.

**If weside MCP is connected but Jira tools are missing**, tell the user:

> "Jira is not connected via your weside Companion. To enable it: weside.ai → Integrations → connect Jira, then activate it for your Companion."
