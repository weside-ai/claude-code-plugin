// The we plugin's $.state contract (the /flow and /board panes).

export type FlowPhase = 'idea' | 'draft' | 'refined' | 'dev' | 'ci' | 'ci-red' | 'ready' | 'merged' | 'closed'

export type FlowLight = 'done' | 'active' | 'red' | 'todo' | 'skip'

// One step /we:master walks a story through, its lamp and what the evidence says.
export type FlowStage = { name: string; light: FlowLight; note: string }

export type FlowRow = {
  key: string
  title: string
  phase: FlowPhase
  stages: FlowStage[]
  pr?: number
  // The plan's `epic:`, shown when the story is asked for on its own.
  epic?: string
  worktree?: string
  branch?: string
}

// One asked key: an epic with its stories, or a single story as a group of one.
export type FlowGroup = {
  key: string
  epicTitle?: string
  rows: FlowRow[]
}

export type FlowView = {
  keys: string[]
  // Where the keys came from when /flow ran without one ("branch feat/PROJ-1-x", "conversation").
  source?: string
  groups: FlowGroup[]
  updatedAt: number
  error?: string
  isLoading: boolean
}

// /flow's section Crew flow: the fields of `flow_intervals.py --snapshot` it shows (the script owns them).
export type CrewFlowNow = {
  who: string
  group?: string | null
  starter?: string | null
  kind: string
  since: string
  waiting_on?: string | null
  key?: string | null
  label?: string | null
}

export type CrewFlowHead = {
  pr: number
  start: string
  end: string
  queue_s: number
  run_s: number
  open: boolean
}

export type CrewFlowView = {
  path?: string
  project?: string
  generatedAt?: string
  // `CI wait: …`, the snapshot's own header line
  ciLine?: string
  now: CrewFlowNow[]
  ci: { number: number; title?: string; heads: CrewFlowHead[] }[]
  gaps: string[]
  page?: string
  error?: string
  isRefreshing: boolean
}

// /board: the file an orchestrator session keeps (docs/board.md), as the pane reads it.
export type BoardQueueItem = {
  id?: string
  session?: string | null
  key?: string | null
  ask?: string | null
  since?: string | null
  recommendation?: string | null
  // `merge-go`, `plan`, … (`board.py ask --cause`).
  cause?: string | null
  // The open PR a merge question is about, and its one-way class: Accept reads Go beside the link.
  pr_url?: string | null
  one_way?: string | null
  // `task` (`board.py ask --kind task`): the pane offers Taken instead of Accept.
  kind?: string | null
  // Where the ask's fact comes from (`--source`), shown under the ask.
  source?: string | null
  // The member who owns the subject (`--owner`/`--component`): the deliverer carries the answer there too.
  owner?: string | null
  // A question `board.py ask --to` sent to a human on another machine: that human's slug and name, and
  // the ticket label. The pane shows it waiting on that human, with Withdraw only.
  to?: string | null
  to_name?: string | null
  label?: string | null
  // Who receives the answer (`board.py ask`): `answer_to: asker` (the default; `board.answer_to:
  // coordinator` opts out) sends it to the asker directly and the coordinator a one-line copy; `starter`
  // takes it when the asker is gone; `asker_id` is the asking session's id.
  answer_to?: string | null
  starter?: string | null
  asker_id?: string | null
}

export type BoardSession = {
  name: string
  role?: string | null
  companion?: string | null
  parent?: string | null
  keys?: string[] | null
  topic?: string | null
  now?: string | null
  state?: string | null
  pr?: number | null
  priority?: number | null
  direction?: string | null
  note?: string | null
  // Restore fields the orchestrator keeps for itself (`--resume <session_id>` in `cwd`); the pane never shows them.
  cwd?: string | null
  session_id?: string | null
  // When the line was last written (`board.py set` stamps it, UTC minute); the pane shows its age.
  updated_at?: string | null
  // In this state since (`YYYY-MM-DDTHH:MMZ`); the age's fallback where `updated_at` is missing.
  since?: string | null
  // A ready tree of the work in progress, for a repo without plan files; it replaces the one the pane derives.
  work?: WorkNode[] | null
}

// One node of a master's work tree (docs/board.md § Work): a saga holds epics, an epic its stories.
// A `key` node is a ticket key without a plan file.
export type WorkNode = {
  kind: 'saga' | 'epic' | 'story' | 'key'
  key?: string
  title?: string
  status?: string
  // A story's /flow phase, which picks its lamp; merged stories only count in their epic's line.
  phase?: FlowPhase
  // An epic's finish line (epic-plan.md § Finish line): line stories merged of all, open extensions, start date.
  line?: { merged: number; total: number }
  extensions?: number
  created?: string
  children?: WorkNode[]
}

// The work tree per master, derived when its box opens (hooks/board/work.ts).
export type BoardWork = {
  nodes: WorkNode[]
  at: number
  error?: string
  isLoading?: boolean
}

export type BoardWorkView = Record<string, BoardWork>

// One item of the board's `news` (docs/board.md § News): a title line, an optional body, and a Read button.
export type BoardNewsKind = 'info' | 'gate' | 'todo'

export type BoardNewsItem = {
  id: string
  title: string
  body?: string
  ts?: string
  kind?: BoardNewsKind
  // The item's `kind` as written when it is none of the three (`decision`, `sample`, `escalation`,
  // `returned`, …): it decides the item's shelf (board.ts newsShelf).
  rawKind?: string
}

// One line of the folded log under the news (docs/board.md § News): the board's `log`, an older news item
// without an id, or a news item that is not for the owner.
export type BoardLogItem = {
  id?: string
  title: string
  body?: string
  ts?: string
  kind?: string
}

// `staging`: the booking and acceptance board.py mirrors from the crew repo's issues (docs/board.md § Staging).
export type BoardStaging = {
  booking?: { holder: string; until?: string; issue?: number }
  acceptance?: { rc: string; opened?: string; due?: string; pastSla: boolean; issue?: number }
  slaHours?: number
}

export type BoardFile = {
  updated?: string
  updatedBy?: string
  queue: BoardQueueItem[]
  sessions: BoardSession[]
  // `priorities` (a list or one string), joined into one line.
  priorities?: string
  // `news`: items the owner reads and acknowledges, each with its own id.
  news: BoardNewsItem[]
  // `log`: what board.py keeps for the record (decisions, samples), plus `news` items without an id.
  log: BoardLogItem[]
  // `notes`: the older free-text field, drawn as a collapsed block under the news.
  notes?: string
  // `answer_prompts`: the orchestrator's own wording of the prompts a press sends.
  answerPrompts?: Partial<Record<BoardPromptKind, string>>
  staging?: BoardStaging
  // `session_age_hours`: when a session line's age turns grey and when red and stale.
  sessionAgeHours?: SessionAgeHours
}

export type SessionAgeHours = { grey: number; stale: number }

// What hooks/board/probe.py prints per running session: verdict-sized facts, no environment values.
export type LiveSession = {
  name?: string | null
  // The transcript's id; the pane finds its own session's name by it.
  sessionId?: string | null
  pid?: number | null
  kind?: string | null
  status?: string | null
  state?: string | null
  weRole?: 'master' | 'worker' | 'other' | null
  profile?: string | null
  envRead?: boolean
  mode?: string | null
  // From the launcher's marker in the session's tree, when it names the session.
  role?: string
  starter?: string
  tree?: string
}

export type BoardView = {
  path?: string
  board?: BoardFile
  mtimeMs: number
  readAt: number
  isMissing?: boolean
  error?: string
}

// One line of the answers file, <stem>-answers.jsonl (docs/board.md): a press of Accept, Deny, Follow-up, Update or
// Withdraw (a question sent to another human) on a question, of Read on a news item, or Refresh's
// request to the coordinator to rebuild the board (`rebuild`, id `rebuild`), or `board.py close-merged`'s
// close of a merge-go question whose PR merged (`pr_merged`, the owner's hand merge) or closed (`pr_closed`).
export type BoardAnswerKind = 'accept' | 'deny' | 'followup' | 'update' | 'withdraw' | 'read' | 'rebuild' | 'pr_merged' | 'pr_closed'
// The answers the deliverer carries; Read only appends its line.
export type BoardDeliveredKind = Exclude<BoardAnswerKind, 'read'>
// The texts a delivery sends, each overridable by the board's `answer_prompts`: one per delivered kind
// for the orchestrator (and the asker), `update_asker`, what Update asks of the asking session, and the
// two Accepts with a meaning of their own: `accept_hand` (Go on a one-way merge-go with its PR, `{pr}`
// standing for the PR link: the asking session arms with `arm_pr.sh <PR>`) and `accept_task`
// (Taken on a task). On a question with `answer_to: asker`, Follow-up sends `followup` to the asker (complete
// the question, offer to talk) and `followup_route` to the coordinator (`{who}`: whom the owner talks to).
export type BoardAcceptVariant = 'accept_hand' | 'accept_task'
export type BoardPromptKind = BoardDeliveredKind | 'update_asker' | BoardAcceptVariant | 'followup_route'

export type BoardAnswer = {
  id: string
  answer: BoardAnswerKind
  ts: string
  session?: string | null
  // `chat` for a line `board.py answer` wrote back from a chat; a pane press has none. Older hand
  // lines may carry free text here.
  via?: string | null
  // The owner's own words, when `board.py answer --quote` gave them.
  quote?: string | null
}

// One row of <stem>-deliveries.jsonl beside the answers file (docs/board.md § Answers): whether one
// answer line reached one recipient. Readers fold the rows of one key (id, answer_ts, role) to the
// newest by `ts`. The first row the deliverer ever writes is `{ "epoch": ts }` instead.
export type BoardDeliveryRole = 'coordinator' | 'asker' | 'owner' | 'starter' | 'route'

export type BoardDelivery = {
  id: string
  // The answer line's `ts`, the key's second half; `click_ts` is the same moment, kept for the latency.
  answer_ts: string
  to: string
  role: BoardDeliveryRole
  click_ts: string
  ts: string
  delivered: boolean
  reason?: string
}

// The ledger as the pane reads it: the folded row per key, and the epoch the deliverer started at.
export type BoardDeliveriesView = {
  path: string
  mtimeMs: number
  epoch?: string
  rows: Record<string, BoardDelivery>
}

// The newest answer per question id, read from the answers file beside the board file.
export type BoardAnswersView = {
  path: string
  mtimeMs: number
  byId: Record<string, BoardAnswer>
}

export type LiveView = {
  sessions: LiveSession[]
  at: number
  error?: string
}

// One live session of `scripts/crew_view.py --json` (its docstring owns the fields), schema 1; `age` is
// added by `command_center/zentrale.py` (crew_view.py age_text), the one age format the pane prints.
export type CrewEntry = {
  name: string
  session_id: string
  kind: string
  role: string
  state: string
  doing: string | null
  keys: string[]
  waiting_on: string | null
  blocked_kind: string | null
  since: string | null
  age_s: number | null
  age?: string
  plugin: string
  starter: string | null
  group: string | null
  waits: boolean
}

// One open end of `command_center/open_ends.py` (its docstring owns the row contract), schema 1.
export type ZentraleRow = {
  kind: string
  item: string
  title: string
  holder: string
  for: string
  master: string
  since: string
  since_note: string
  age_s: number | null
  age?: string
  source: string
  classes: string[]
  red: boolean
}

export type ZentraleAccount = {
  name: string
  active: boolean
  in_rotation: boolean
  five_hour: { pct: number | null; resets_at: string | null }
  seven_day: { pct: number | null; resets_at: string | null }
  threshold: number | null
  status: string
  measured_at: string | null
  age_s: number | null
  stale: boolean
  red: boolean
}

// `command_center/zentrale.py --json` (its docstring owns the fields), schema 1.
export type ZentraleDoc = {
  schema_version: number
  project: string | null
  built_at: string
  fast: boolean
  header: string[]
  gaps: string[]
  sources: Record<string, { fetched_at: string | null; gap: string | null }>
  sections: {
    owner: ZentraleRow[]
    red: ZentraleRow[]
    waiting: ZentraleRow[]
    working: CrewEntry[]
    ci: {
      repos: { repo: string; fetched_at: string | null; default_head: string; checks: { pr: number; name: string; status: string; since: string | null; age_s: number | null; age?: string }[] }[]
      locks: string
    }
    accounts: ZentraleAccount[]
  }
}

// The Zentrale pane's view: the last document, the board it read, when it was read; the swimlanes'
// intervals (`flow_intervals.py --json`) once asked; which face shows.
export type ZentraleView = {
  board?: string
  doc?: ZentraleDoc
  at: number
  error?: string
  lanes?: { intervals: { who: string; kind: string; start: string; end: string }[]; at: number; error?: string }
  face: 'sections' | 'lanes'
  hours: 8 | 24
  // the web view (`scripts/command_center/crewd.py probe`): its configured URL and whether it answers here
  web?: { url: string | null; alive: boolean }
}

declare module 'claude-code' {
  interface PluginState {
    we: {
      flowBoard: FlowView | null
      flowCrew: CrewFlowView | null
      boardView: Shaped<BoardView | null>
      boardLive: Shaped<LiveView | null>
      boardAnswers: Shaped<BoardAnswersView | null>
      boardDeliveries: Shaped<BoardDeliveriesView | null>
      boardOpen: boolean
      boardRestOpen: boolean
      boardNotesOpen: boolean
      boardLogOpen: boolean
      boardWork: Shaped<BoardWorkView | null>
      boardWorkOpen: Shaped<string[]>
      zentraleView: Shaped<ZentraleView | null>
      zentraleOpen: boolean
    }
  }
}
