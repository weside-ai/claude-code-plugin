# Ticketing Detection

Detect the available ticketing tool in priority order:

1. **weside MCP** (`JIRA_*` Composio tools via `execute_tool`) → Jira (preferred)
2. **Atlassian MCP** (`jira_*` tools) → Jira (fallback)
3. **`gh` CLI** → GitHub Issues
4. **None** → Plan-only mode (no ticket, just `docs/plans/`)

Skills use generic actions ("Create ticket", "Move to In Progress") — never tool-specific API calls. Claude maps the generic action to the best available tool.

**Reading a ticket (any skill that loads one):** fetch the ticket **including its comments** — summary/description alone is never the full ask. Comments carry the later corrections, scope cuts, agreed edge cases and answers to open questions; when a comment contradicts the description, the **newest** statement wins and you name the conflict to the user instead of silently picking one. Jira via Composio: `JIRA_GET_ISSUE` with the comment field/expand (inspect via `get_tool_schema`), or `JIRA_GET_COMMENTS` where a separate call is needed; Atlassian MCP: `jira_get_issue` with `comment_limit` > 0; GitHub Issues: `gh issue view {N} --comments`.

Ticket **content** rules (behavioural contracts, testable ACs, no file paths/line numbers) are owned by `ticket-briefs.md`.

**How Composio Jira works (path 1):** tools are called via `execute_tool(name="JIRA_CREATE_ISSUE", arguments='{...}')`. Tool names use the uppercase `JIRA_` prefix. Schemas are self-describing — use `get_tool_schema(name="JIRA_...")` to inspect parameters.

**Ticket transition (any skill that moves a ticket):** find the matching transition (names vary: "In Progress", "Start Progress", "In Bearbeitung"), execute it, then **verify** the ticket actually moved (re-fetch status) and retry once with a different transition name if not. Soft-fail loud (log a warning, continue) only when the workflow/permissions genuinely reject the move. GitHub Issues (no status transitions) / no ticketing tool → skip silently.

**Transition first, comment second — never in one call.** A transition's optional
`comment` field wants Atlassian Document Format, not the Markdown or Wiki Markup the
description fields take, so passing prose there fails with *"Operation value must be an
Atlassian Document"* and the transition does not happen either. Move the ticket bare, then add
the note with the dedicated add-comment tool. Two calls, and a failed comment can no longer
cost you the status change.

**If weside MCP is connected but Jira tools are missing**, tell the user:

> "Jira is not connected via your weside Companion. To enable it: weside.ai → Integrations → connect Jira, then activate it for your Companion."
