---
name: council
description: >
  Convenes role lenses in a live team that message each other; the lead synthesises agreement,
  tension, recommendation. Triggers: "/we:council", "convene a council", "deliberate on", "ask the
  team".
---

# /we:council — multi-voice deliberation

You are the lead and the orchestrator: spawn one `we:council-<role>` member per role in one message, let them deliberate via `SendMessage`, close when ripe, collect final positions, write the synthesis.
Members run on Sonnet by their agent files (Foxy 27.09.2026: deliberation is not implementation); do not pass `model` in the spawn.
You never speak as a member. The recommendation goes to the user, who decides; it never auto-executes, and the council writes no file and no ticket.
Always tear the members down, also on a failure path: a leaked member blocks the next council in the session.
Wanted stop: the synthesis. Every other status note goes with the next tool call.

Rosters, role shells and the four synthesis headings: `${CLAUDE_PLUGIN_ROOT}/references/apo-hierarchy.md` § Council rosters and synthesis.
Member brief: `${CLAUDE_PLUGIN_ROOT}/skills/council/references/brief.md`.

```text
/we:council "<topic>" [--council=role,role | --meeting=vision|saga|epic|story]
```

## 1. Topic and roster

- No topic: ask for one.
- Roles, first hit wins: `--council=`; `--meeting=<type>` → `.weside/config.json` `council.meetings.<type>`;
  `council.default`; the shipped defaults. A config with the pre-4-altitude keys (in leading-companions,
  weside-cli, weside-infrastructure, weside-landing, measured 27.09.2026) maps `saga` → `initiative` and
  `story` → `refinement`; say once that the key wants renaming. `epic` has no old key: use `council.default`.
- `orchestrator` in a resolved roster is you: drop it and note it for the synthesis. Spawn
  `we:council-orchestrator` as a member only when `--council=` names it.
- A role without a shipped shell (a custom slug) is skipped and named in the synthesis.

## 2. Member source

Read `~/.claude/settings.json` → `pluginConfigs["we@weside-ai"].options.loadCouncilFromWeside`
(missing means `true`).

- `false` (Foxy's setting on 27.09.2026): every member is the generic shell. When
  `.weside/council.json` names a member for the role with a `lens` string, the brief carries it.
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
Agent(name: "<role-with-hyphens>", subagent_type: "we:council-<role-with-hyphens>",
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

The four headings from `apo-hierarchy.md`, verbatim, because `/we:meet` parses them:

- `## Council Perspectives`: one line per member's final position; an absent member is named as absent,
  never given an invented position. Say how the council closed (quiescence or a cap).
- `## Agreement`: where the members genuinely converge.
- `## Tension`: each disagreement as a trade-off ("A favours X because …, B favours Y because …"), not a
  vote count. Name consensus theatre (everyone agreed at once: the roster lacked the dissenting lens) and
  off-lens contributions, so the user can discount them.
- `## Recommendation`: one concrete next move that resolves the tensions, naming what it trades and
  every decision the user must make.

Closing notes, one line each when they apply: "Orchestrator role: handled by the lead session." and
the woken members from `weside-members.md`. A materialised Companion in this session speaks the
synthesis in its voice; the headings stay verbatim.

## 7. Teardown

1. `SendMessage(to: <name>, message: "SESSION COMPLETE — you may stop.", summary: "shutdown_request")` to
   every member, absent ones included.
2. Verify each stopped; `TaskStop` any that did not within ~30 s.
3. `tmux list-panes -a`: kill an idle pane left by a member, never the lead's own.
