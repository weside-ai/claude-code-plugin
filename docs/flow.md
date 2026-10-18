# The flow pane: `/flow`

`/flow` opens a pane beside the transcript with one traffic light per step of the build pipeline,
for one story, every story of an epic, or whatever the current session works on. It reads git and
GitHub itself and refreshes every two minutes; no agent feeds it and nothing has to run.

```text
◆ PROJ-10
██████████████████████████░░░░  13/15 merged · 1 open · 1 red

Epic PROJ-10  Channels everywhere
[ Epic status ] [ Orchestrate ]
╭──────────────────────────────────────────────────────────╮
│ PROJ-14  CI red  #5090                                   │
│ One bot identity per guild                               │
│ ● Plan  ● Approval  ● Build  ● PR  ◉ CI  ◉ Review  ○ Merge │
│                                                          │
│ ● Plan     story plan on the default branch              │
│ ● Approval status: approved                              │
│ ● Build    14 commits                                    │
│ ● PR       #5090                                         │
│ ◉ CI       ✗ CI Summary · 2 running · 11/14 ✓            │
│ ◉ Review   Claude running · Codex ✓                      │
│ ↳ /work/repo-PROJ-14                                     │
│ [ Standup ] [ Fix CI ]                                   │
╰──────────────────────────────────────────────────────────╯
✓ PROJ-12  Discord groups like Telegram  #5072
…
```

## Opening it

| Call | Shows |
|---|---|
| `/flow PROJ-10` | an epic (its plan has `ticket: PROJ-10`) with every story whose `epic:` names it, or a single story |
| `/flow PROJ-10 PROJ-21` | several keys, one block each (at most six) |
| `/flow` | what this session works on, see below |

Without a key, `/flow` takes the first source that names one: the statusline focus
`/we:orchestrate` writes when it pushes (`~/.claude/we-focus/<session>.json`), the current branch
(`feat/PROJ-14-…`), the keys you typed or a skill ran on in this conversation (newest first), and
last the keys the pane showed before. The pane says which source it used. With
`ticketing.project_key` in `.weside/config.json` only keys of that project count, in any case.

## The lights

Seven lamps, in the order `/we:orchestrate` walks a story through them:

| Lamp | Green when | Yellow (current) | Red (stuck) |
|---|---|---|---|
| Plan | `docs/plans/<KEY>-story.md` is on the default branch | no plan yet: the Lead's refine lane writes one | — |
| Approval | the plan says `status: approved` | the plan waits for the owner's approval | — |
| Build | a PR exists | commits on a branch, no PR yet | branch left after a closed PR |
| PR | a PR is open (not a draft) or merged | a draft PR | closed without a merge |
| CI | every required check except the reviews passed | checks running | a check failed |
| Review | the Claude Review check passed | it runs | it failed; Codex is shown beside it, advisory |
| Merge | merged | auto-merge armed, or green and waiting for a user merge | conflicts with the default branch |

`○` is a step not reached yet, `–` one that was skipped (a story built without a plan file). Under
the lamps each reached step names its evidence: commit count, PR number, the failed check by name.
Open stories come first, the most urgent on top (CI red, closed PR, CI running, waiting for merge,
in development, ready to build, plan draft, no plan); merged stories follow as one line each.

## Buttons

A button runs its command as if you typed it, once the session is idle:

| Button | Where | Runs |
|---|---|---|
| Standup | every open story | `/we:standup <KEY>` |
| Refine | plan missing or not approved | `/we:orchestrate <KEY>` |
| Build | approved, nothing built | `/we:orchestrate <KEY>` |
| Fix CI | CI, review or merge red | `/we:ci-review <PR>` |
| Epic status | epic header | `/we:epic <KEY>` |
| Orchestrate | epic header, while a story is open | `/we:orchestrate <KEY>` |
| Refresh (`r`) | footer | reads git and GitHub again |

## Data sources

Every refresh, in the repo the session runs in:

- `git fetch origin`, then the plan files on the default branch (`origin/HEAD`): `story`, `epic`,
  `status` and the first heading, via `git grep`.
- Local and remote branches whose name holds the key, and how many commits each has beyond the
  default branch; `git worktree list` for the worktree path.
- `gh pr list` for every key: state, draft, checks, auto-merge, merge state.

The pane does not read the ticketing tool: a story that exists only as a ticket, without a plan file
or a branch, is not listed. The summary also shows in the statusline.

## Requirements

Claude Code with function hooks (2.1.302 or later), `git`, and `gh` signed in. The pane is part of
the plugin's hooks module (`we/hooks/flow/`); it loads with the plugin and needs no setting.
