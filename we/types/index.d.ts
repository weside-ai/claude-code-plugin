// The we plugin's $.state contract (the flow pane's board).

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

declare module 'claude-code' {
  interface PluginState {
    we: { flowBoard: FlowView | null }
  }
}
