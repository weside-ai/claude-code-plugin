---
name: ticketing
description: Reading a ticket with its comments and moving it safely. Shared by /we:orchestrate and /we:develop.
---

# Ticketing

- Tool, in this order: the weside MCP (`execute_tool` with `JIRA_*`), the Atlassian MCP
  (`jira_*`), `gh issue`, else plan-only (no ticket, say so once). `.weside/config.json`
  `ticketing` names the project.
- A ticket is read with its comments (Atlassian: `jira_get_issue` with `comment_limit` > 0;
  GitHub: `gh issue view <n> --comments`). When a comment contradicts the description or the plan,
  the newest statement wins and the conflict is named, never picked silently.
- A transition is verified by re-reading the status; retry once with another transition name, then
  warn and continue. Transition first, comment second: a transition's `comment` field wants
  Atlassian Document Format, and prose there fails the transition too.
- Status names per repo live in `.weside/orchestrate.md` § Ticket states.
