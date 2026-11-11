---
name: ticketing
description: Reading a ticket with its comments and moving it safely. Shared by /we:master and /we:develop.
---

# Ticketing

- Tool, in this order: the weside MCP (`execute_tool` with `JIRA_*`), an Atlassian MCP, `gh issue`,
  else plan-only (no ticket, say so once). `.weside/config.json` `ticketing` names the project the
  skills read; the crew file's `board.ticketing` (`none` or `jira`) decides whether `board.py`
  prints `carry:`. Two keys, two readers: the skills read `ticketing`, `board.py` reads `board.ticketing`.
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
- Status names: the crew file's `board.states` where the repo has one (`board.py` reads them); else
  the repo's `.weside/orchestrate.md` § Ticket states.
- Every move follows the entry rule of its state (L0 §Lifecycle). With a crew file that sets
  `board.ticketing`, a move goes through `board.py select` or `board.py move` (`docs/board.md`
  § Moves), and the session carries its `carry:` line with its ticketing tool, then verifies by
  re-reading. Some skills move by ticketing tool instead, and `board.py check` shows where board and
  ticket differ: the master moves Selected → In Progress when it pulls a
  story, `/we:merged` moves a merged and linked story to In Review
  (`${CLAUDE_PLUGIN_ROOT}/skills/merged/SKILL.md` § 5), and Done comes only from a receipt report or an
  acceptance comment.
- Several humans (`docs/board.md` § Several humans): `board.py select` carries the transition, then
  the comment `selected by <role>@<human>, …`; `board.py claim` a comment; `board.py ask --to` a
  comment, then a label (`{"op": "label", "key", "add"}`: add it to the ticket's labels, keep the
  others); `board.py reply` and `withdraw` an `unlabel` (`{"op": "unlabel", "key", "remove"}`).
  The reads `board.py signals`, `claim`, `inbox`, `select`, `move` and a merge-go `ask` print
  (`search`: run the JQL, give back each hit's key and the time of the change; `read`: the
  ticket's status, labels and comments with created and author, the author as the account's
  email, else its accountId, never the display name) go back as `--input FILE`; Rovo: `searchJiraIssuesUsingJql`, the labels from
  `getJiraIssue`, the comments from `listJiraIssueComments`; `jira_*`: `jira_search`,
  `jira_get_issue` with `comment_limit`. `board.py signals` refuses while `board.jql_scope` is unset, so no
  query reads every project. A ticket status that no `board.states` entry maps (a "Blocked")
  refuses a move and a merge-go: map it in the crew file. The In Test status exists only where
  `board.states.in_test` names it.
