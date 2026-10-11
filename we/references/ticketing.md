---
name: ticketing
description: Reading a ticket with its comments and moving it safely. Shared by /we:orchestrate and /we:develop.
---

# Ticketing

- Tool, in this order: the weside MCP (`execute_tool` with `JIRA_*`), the Atlassian Rovo MCP
  (plugin `atlassian@claude-plugins-official`, tools `mcp__plugin_atlassian_atlassian__*`), `gh issue`,
  else plan-only (no ticket, say so once). `.weside/config.json` `ticketing` names the project.
- Rovo: every call takes a `cloudId` from `getAccessibleAtlassianResources`; bodies are Markdown
  (`contentFormat` defaults to `markdown`), never Wiki Markup. Issue links go through `executeWrite`
  with `createJiraIssueLink`.
- A ticket is read with its comments (Rovo: `getJiraIssue`, then `listJiraIssueComments` via
  `executeRead` — `getJiraIssue` returns only the count; GitHub: `gh issue view <n> --comments`). When a comment contradicts the description or the plan,
  the newest statement wins and the conflict is named, never picked silently.
- A transition is verified by re-reading the status; retry once with another transition name, then
  warn and continue. Transition first (`transitionJiraIssue`), comment second
  (`addOrEditJiraIssueComment`): a comment inside the transition's `update` can be silently lost.
- Status names per repo live in `.weside/orchestrate.md` § Ticket states.
