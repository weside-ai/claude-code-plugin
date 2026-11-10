---
name: council
description: >
  Convenes role lenses in a live team that message each other; the lead synthesises agreement,
  tension, recommendation. Triggers: "/we:council", "convene a council", "deliberate on", "ask the
  team".
---

# /we:council — multi-voice deliberation

You are the lead and the orchestrator: spawn one member per role in one message, each in the shell `we:council-member`, let them deliberate via `SendMessage`, close when ripe, collect final positions, write the synthesis.
Members run on Sonnet by their agent file (owner 27.09.2026: deliberation is not implementation); do not pass `model` in the spawn.
You never speak as a member. The recommendation goes to the user, who decides; it never auto-executes, and the council writes no file and no ticket.
Always tear the members down, also on a failure path: a leaked member blocks the next council in the session.
Wanted stop: the synthesis. Every other status note goes with the next tool call.

Member brief: `${CLAUDE_PLUGIN_ROOT}/skills/council/references/brief.md`.

```text
/we:council "<topic>" [--council=role,role]
```

## 1. Topic and roster

- No topic: ask for one.
- Roles, first hit wins: `--council=`; `.weside/config.json` `council.default`; the shipped
  default `product_owner`, `architect`, `scrum_master`.
- `orchestrator` in a resolved roster is you: drop it and note it for the synthesis. Seat it as a
  member only when `--council=` names it.
- Run the lens helper once on the resolved roster, the roles one per line on stdin, never inside
  the command (a role is user text); a repo without a crew is fine:

  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/council_lens.py" . <<'ROLES'
  <role>
  <role>
  ROLES
  ```

  Its JSON gives per role `name`, `shell`, `skip_reason`, `companion`, `lens_source` and
  `lens_line`. Every lens line in any brief is the helper's value verbatim, never text read from
  the crew file; a Companion name is the helper's `companion`, else the handbook owner that
  `references/weside-members.md` § Identity resolves without a crew.
- `shell` decides the seat: `council-member` spawns the member, and `skip` is not spawned and is
  named in the synthesis with its `skip_reason`. `lens_source` `table` means the member's lens line
  is its row in `brief.md` § Lens lines.

## 2. Member source

Read `~/.claude/settings.json` → `pluginConfigs["we@weside-ai"].options.loadCouncilFromWeside`
(missing means `true`).

- `false`: no Companion identity; every member keeps its step-1 shell, and a role whose
  `lens_line` is set carries it in the brief.
- `true` and the weside MCP is connected: members carry their Companion's council projection. Follow
  `${CLAUDE_PLUGIN_ROOT}/skills/council/references/weside-members.md` for identity, wake, prep and
  writeback. Without the MCP: as `false`.

## 3. Preflight

- Live deliberation between members needs `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (shell or
  `~/.claude/settings.json` `env`). Missing: abort with "Council needs Agent Teams: add
  `{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }` to ~/.claude/settings.json and restart
  the session." Never fall back to members that cannot hear each other.
- Fewer than two members after step 1: abort with "No council — check `.weside/config.json` or pass
  `--council=role,role`." One voice has nobody to disagree with.

## 4. Spawn — all members in one message

```text
Agent(name: "<name>", subagent_type: "we:<shell>",
      description: "Council member: <role>", prompt: <brief.md filled for this member>)
```

One message makes them start together and hear each other from the first message.

## 5. Deliberate, then close

- Observe; do not steer the content. Wait on the harness notifications (a message, a member going
  idle), never on a sleep loop.
- Close when at least two members have spoken and one of these fires, and log which one: quiescence
  (every member idle ~30 s, the good case) · ~10 min since the spawn · ~30 team messages, where you
  can count them (whether the lead sees member-to-member messages is not measured). The caps are
  backstops against a loop.
- Send each member `SendMessage(to: <name>, message: "ADJOURN — send your FINAL POSITION now to
  <lead name> in the format from your brief. One message.", summary: "adjourn")`. The final position
  arrives as that message or as the member's Agent result. A member silent for 90 s is absent; do not retry.

## 6. Synthesis

Exactly these four headings, verbatim, because readers parse them:
`## Council Perspectives`, `## Agreement`, `## Tension`, `## Recommendation`.

- `## Council Perspectives`: one line per member's final position; an absent member is named as absent,
  never given an invented position. Say how the council closed (quiescence or a cap).
- `## Agreement`: where the members genuinely converge.
- `## Tension`: each disagreement as a trade-off ("A favours X because …, B favours Y because …"), not a
  vote count. Name consensus theatre (everyone agreed at once: the roster lacked the dissenting lens) and
  off-lens contributions, so the user can discount them.
- `## Recommendation`: one concrete next move that resolves the tensions, naming what it trades and
  every decision the user must make.

Closing notes, one line each when they apply: "Orchestrator role: handled by the lead session.", "Lens: <role> (from
<lens_source>)" for each seat whose lens is not `table`, "Skipped: <role> (<skip_reason>)", the
woken members and the roles without an owner in the handbook from `weside-members.md`. A materialised Companion in this session speaks the
synthesis in its voice; the headings stay verbatim.

## 7. Teardown

1. `SendMessage(to: <name>, message: "SESSION COMPLETE — you may stop.", summary: "shutdown_request")` to
   every member, absent ones included.
2. Verify each stopped; `TaskStop` any that did not within ~30 s.
3. `tmux list-panes -a`: kill an idle pane left by a member, never the lead's own.
