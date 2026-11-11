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
  // The open PR a merge question is about, and its one-way class: Accept reads "Yes, I'll do it" beside the link.
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
}

export type BoardView = {
  path?: string
  board?: BoardFile
  mtimeMs: number
  readAt: number
  isMissing?: boolean
  error?: string
}

// One line of the answers file, <stem>-answers.jsonl (docs/board.md): a press of Accept, Deny, Discuss, More info, Update or
// Withdraw (a question sent to another human) on a question, or of Read on a news item.
export type BoardAnswerKind = 'accept' | 'deny' | 'discuss' | 'info' | 'update' | 'withdraw' | 'read'
// The answers the deliverer carries; Read only appends its line.
export type BoardDeliveredKind = Exclude<BoardAnswerKind, 'read'>
// The texts a delivery sends, each overridable by the board's `answer_prompts`: one per delivered kind
// for the orchestrator (and the asker), `update_asker`, what Update asks of the asking session, and the
// two Accepts that mean "I do it myself": `accept_hand` ("Yes, I'll do it" on a one-way merge-go with its
// PR, `{pr}` standing for the PR link) and `accept_task` (Taken on a task).
export type BoardAcceptVariant = 'accept_hand' | 'accept_task'
export type BoardPromptKind = BoardDeliveredKind | 'update_asker' | BoardAcceptVariant

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
export type BoardDeliveryRole = 'coordinator' | 'asker' | 'owner' | 'route'

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

declare module 'claude-code' {
  interface PluginState {
    we: {
      flowBoard: FlowView | null
      boardView: Shaped<BoardView | null>
      boardLive: Shaped<LiveView | null>
      boardAnswers: Shaped<BoardAnswersView | null>
      boardDeliveries: Shaped<BoardDeliveriesView | null>
      boardOpen: boolean
      boardRestOpen: boolean
      boardNotesOpen: boolean
      boardWork: Shaped<BoardWorkView | null>
      boardWorkOpen: Shaped<string[]>
    }
  }
}
