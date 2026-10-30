// The we plugin's $.state contract (the /flow and /board panes).

export type FlowPhase = 'idea' | 'draft' | 'refined' | 'dev' | 'ci' | 'ci-red' | 'ready' | 'merged' | 'closed'

export type FlowLight = 'done' | 'active' | 'red' | 'todo' | 'skip'

// One step /we:orchestrate walks a story through, its lamp and what the evidence says.
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

export type BoardFile = {
  updated?: string
  updatedBy?: string
  queue: BoardQueueItem[]
  sessions: BoardSession[]
  // `priorities` (a list or one string), joined into one line.
  priorities?: string
  // `notes`: a banner the orchestrator wants seen first.
  notes?: string
  // `answer_prompts`: the orchestrator's own wording of the prompts a press sends.
  answerPrompts?: Partial<Record<BoardAnswerKind, string>>
}

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

// One line of board-answers.jsonl (docs/board.md): a press of Accept, Discuss or More info.
export type BoardAnswerKind = 'accept' | 'discuss' | 'info'

export type BoardAnswer = {
  id: string
  answer: BoardAnswerKind
  ts: string
  session?: string | null
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
      boardOpen: boolean
      boardRestOpen: boolean
      boardWork: Shaped<BoardWorkView | null>
      boardWorkOpen: Shaped<string[]>
    }
  }
}
