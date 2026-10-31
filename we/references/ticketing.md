---
name: ticketing
description: Reading a ticket with its comments and moving it safely. Shared by /we:orchestrate and /we:develop.
---

# Ticketing

- Tool, in this order: the weside MCP (`execute_tool` with `JIRA_*`), an Atlassian MCP, `gh issue`,
  else plan-only (no ticket, say so once). `.weside/config.json` `ticketing` names the project.
- An Atlassian MCP is recognised by its tool names, whatever the server prefix: Rovo
  (`getJiraIssue`, `searchJiraIssuesUsingJql`, `transitionJiraIssue`, `addOrEditJiraIssueComment`;
  e.g. the plugin `atlassian@claude-plugins-official`) is preferred, the community server
  (`jira_*`) is accepted.
  - Rovo: every call takes a `cloudId` from `getAccessibleAtlassianResources`; bodies are Markdown
    (`contentFormat` defaults to `markdown`). Comments are read with `listJiraIssueComments` and
    issues linked with `createJiraIssueLink`, both through `executeRead`/`executeWrite`;
    `getJiraIssue` returns only the comment count.
  - `jira_*`: a ticket is read with `jira_get_issue` and `comment_limit` > 0; bodies are Wiki Markup.
  - Other paths (weside MCP, `gh issue`): the body format their tool schema states; GitHub reads
    comments with `gh issue view <n> --comments`.
- A ticket is read with its comments. When a comment contradicts the description or the plan,
  the newest statement wins and the conflict is named, never picked silently.
- A transition is verified by re-reading the status; retry once with another transition name, then
  warn and continue. Transition first, comment second, in two calls: a comment inside the
  transition (Rovo `update`, `jira_*` `comment`) is lost or fails the whole transition.
- Status names per repo live in `.weside/orchestrate.md` § Ticket states.
- Only `/we:merged` moves a ticket to Done, and only while `ticketing.after_merge` is `"done"`
  (the default); `"in_review"` keeps it in In Review (`${CLAUDE_PLUGIN_ROOT}/skills/merged/SKILL.md` § 5).
