// Pure logic of the /board pane: parse the orchestrator's board file, order it, judge each session's start mode.
import type { BoardAnswer, BoardAnswerKind, BoardFile, BoardQueueItem, BoardSession, LiveSession } from '../../types'

const MIN = 60_000
const DAY = 86_400_000
const KINDS: readonly BoardAnswerKind[] = ['accept', 'discuss', 'info']

const promptsOf = (raw: unknown): Partial<Record<BoardAnswerKind, string>> | undefined => {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const out: Partial<Record<BoardAnswerKind, string>> = {}
  for (const kind of KINDS) {
    const text = (raw as Record<string, unknown>)[kind]
    if (typeof text === 'string' && text.trim()) out[kind] = text
  }
  return out
}

export const parseBoard = (text: string): BoardFile => {
  const raw = JSON.parse(text) as unknown
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('board file is no JSON object')
  const file = raw as Record<string, unknown>
  return {
    updated: typeof file.updated === 'string' ? file.updated : undefined,
    updatedBy: typeof file.updated_by === 'string' ? file.updated_by : undefined,
    queue: Array.isArray(file.owner_queue) ? (file.owner_queue as BoardQueueItem[]) : [],
    sessions: Array.isArray(file.sessions) ? (file.sessions as BoardSession[]) : [],
    answerPrompts: promptsOf(file.answer_prompts),
  }
}

// The answers file sits beside the board file (docs/board.md § Answers).
export const answersPathOf = (boardPath: string) => `${boardPath.replace(/[^/]*$/, '')}board-answers.jsonl`

// The newest answer per question id: later lines win; a line that is no answer is skipped.
export const lastAnswers = (text: string): Record<string, BoardAnswer> => {
  const out: Record<string, BoardAnswer> = {}
  for (const line of text.split('\n')) {
    if (!line.trim()) continue
    try {
      const a = JSON.parse(line) as Partial<BoardAnswer>
      if (typeof a.id === 'string' && KINDS.includes(a.answer as BoardAnswerKind) && typeof a.ts === 'string') {
        out[a.id] = { id: a.id, answer: a.answer as BoardAnswerKind, ts: a.ts, session: a.session ?? null }
      }
    } catch {
      // A torn or foreign line: the answers around it still count.
    }
  }
  return out
}

// The prompt a press sends into the orchestrator's own session; the board's `answer_prompts` replaces
// a default, `{id}` standing for the question's id.
const DEFAULT_PROMPT: Record<BoardAnswerKind, string> = {
  accept: '{id}: proposal accepted',
  discuss: "{id}: let's talk about it",
  info: '{id}: I need more information',
}

export const answerPrompt = (answer: BoardAnswerKind, id: string, own?: Partial<Record<BoardAnswerKind, string>>) =>
  (own?.[answer] ?? DEFAULT_PROMPT[answer]).split('{id}').join(id)

// This session's name as `claude agents` lists it, matched on the transcript id.
export const ownName = (live: readonly LiveSession[], sessionId: string): string | undefined =>
  live.find(s => s.sessionId === sessionId && !!s.name)?.name ?? undefined

export type Freshness = { label: string; level: 'ok' | 'warn' | 'stale' }

export const freshness = (updated: string | undefined, now: number): Freshness | undefined => {
  const at = updated ? Date.parse(updated) : NaN
  if (Number.isNaN(at)) return undefined
  const minutes = Math.max(0, Math.floor((now - at) / MIN))
  const label = minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`
  return { label, level: minutes >= 480 ? 'stale' : minutes >= 120 ? 'warn' : 'ok' }
}

// `since` is a calendar date (YYYY-MM-DD): whole days between it and today.
export const ageDays = (since: string | undefined, now: number): number | undefined => {
  const day = since?.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!day) return undefined
  const today = new Date(now)
  const start = Date.UTC(Number(day[1]), Number(day[2]) - 1, Number(day[3]))
  const end = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.max(0, Math.round((end - start) / DAY))
}

export const sortQueue = (queue: readonly BoardQueueItem[]): BoardQueueItem[] =>
  [...queue].sort((a, b) => (a.since ?? '9999').localeCompare(b.since ?? '9999'))

const bySession = (a: BoardSession, b: BoardSession) => {
  const waits = Number(b.state === 'wait-owner') - Number(a.state === 'wait-owner')
  if (waits) return waits
  const pa = typeof a.priority === 'number' ? a.priority : Infinity
  const pb = typeof b.priority === 'number' ? b.priority : Infinity
  return pa === pb ? 0 : pa < pb ? -1 : 1
}

// A master by role, or by being named as some session's parent (docs/board.md).
export const isMasterOf = (session: BoardSession, all: readonly BoardSession[]) =>
  session.role === 'master' || all.some(s => s.parent === session.name)

export type SessionGroup = { head?: BoardSession; workers: BoardSession[] }

// Masters first, each with its workers under it; workers whose parent is not on the board last, headless.
export const groupSessions = (sessions: readonly BoardSession[]): SessionGroup[] => {
  const names = new Set(sessions.map(s => s.name))
  const isChild = (s: BoardSession) => !!s.parent && names.has(s.parent)
  const heads = sessions.filter(s => !isChild(s) && isMasterOf(s, sessions)).sort(bySession)
  const groups: SessionGroup[] = heads.map(head => ({
    head,
    workers: sessions.filter(s => s.parent === head.name).sort(bySession),
  }))
  const placed = new Set(groups.flatMap(g => [g.head!.name, ...g.workers.map(w => w.name)]))
  const rest = sessions.filter(s => !placed.has(s.name)).sort(bySession)
  if (rest.length) groups.push({ workers: rest })
  return groups
}

export type Lamp = 'runs' | 'waits' | 'quiet' | 'unknown'

export const lampOf = (state: string | undefined | null): Lamp => {
  if (state === 'build' || state === 'ci') return 'runs'
  if (state === 'wait-owner') return 'waits'
  if (state === 'idle' || state === 'done') return 'quiet'
  return 'unknown'
}

export type Liveness = 'busy' | 'waiting' | 'idle' | 'blocked' | 'gone'

const LIVE_RANK: Record<Liveness, number> = { busy: 0, waiting: 1, blocked: 2, idle: 3, gone: 4 }

const livenessOf = (s: LiveSession): Liveness => {
  if (s.status === 'busy' || s.state === 'working') return 'busy'
  if (s.status === 'waiting') return 'waiting'
  if (s.state === 'blocked') return 'blocked'
  if (s.pid === null || s.pid === undefined) return 'gone'
  return 'idle'
}

// One live entry per name; where a name runs twice (a parked job and its new copy) the liveliest wins.
export const liveByName = (live: readonly LiveSession[]): Map<string, LiveSession & { liveness: Liveness }> => {
  const out = new Map<string, LiveSession & { liveness: Liveness }>()
  for (const s of live) {
    if (!s.name) continue
    const entry = { ...s, liveness: livenessOf(s) }
    const had = out.get(s.name)
    if (!had || LIVE_RANK[entry.liveness] < LIVE_RANK[had.liveness]) out.set(s.name, entry)
  }
  return out
}

export const SHORT_MODE: Record<string, string> = {
  bypassPermissions: 'bypass',
  acceptEdits: 'accept',
  default: 'prompting',
  plan: 'plan',
  auto: 'auto',
  dontAsk: 'dontAsk',
}

export const majorityMode = (live: Iterable<LiveSession>): string | undefined => {
  const count = new Map<string, number>()
  for (const s of live) if (s.mode) count.set(s.mode, (count.get(s.mode) ?? 0) + 1)
  return [...count.entries()].sort((a, b) => b[1] - a[1])[0]?.[0]
}

// claude-swap names a profile folder `<n>-<account>`: the option names the account, with or without the number.
export const isMasterProfile = (profile: string | null | undefined, masterProfile: string | undefined) =>
  !!masterProfile && !!profile && (profile === masterProfile || profile.endsWith(`-${masterProfile}`))

export type StartMode = { level: 'ok' | 'warn' | 'bad' | 'none'; reason: string; mode?: string }

// The start-mode lamp. With `masterProfile` set it turns red when a master runs without WE_ROLE=master
// or outside that profile, or a worker inside it; always yellow when only the permission mode differs
// from what most sessions run.
export const startModeOf = (
  session: BoardSession,
  isMaster: boolean,
  live: LiveSession | undefined,
  majority: string | undefined,
  masterProfile: string | undefined,
): StartMode => {
  if (!live || !live.envRead) return { level: 'none', reason: '' }
  const mode = live.mode ? SHORT_MODE[live.mode] ?? live.mode : undefined
  const reasons: string[] = []
  if (masterProfile) {
    const inMaster = isMasterProfile(live.profile, masterProfile)
    if (isMaster) {
      if (live.weRole !== 'master') reasons.push(live.weRole ? 'WE_ROLE is not master' : 'WE_ROLE missing')
      if (!inMaster) {
        reasons.push(live.profile && live.profile !== 'other'
          ? `profile ${live.profile}, not the master profile`
          : 'not in the master profile')
      }
      if (reasons.length) reasons[reasons.length - 1] += ' — restart it as a master'
    } else if (inMaster && (session.role === 'worker' || live.weRole === 'worker')) {
      reasons.push('worker in the master profile — it bills the master account')
    }
  }
  if (reasons.length) return { level: 'bad', reason: reasons.join(' · '), mode }
  if (live.mode && majority && live.mode !== majority) {
    return { level: 'warn', reason: `mode ${mode} differs (most run ${SHORT_MODE[majority] ?? majority})`, mode }
  }
  return { level: 'ok', reason: 'ok', mode }
}
