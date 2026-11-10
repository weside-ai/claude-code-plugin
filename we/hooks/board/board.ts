// Pure logic of the /board pane: parse the orchestrator's board file, order it, judge each session's start mode.
import type {
  BoardAnswer, BoardAnswerKind, BoardDeliveredKind, BoardFile, BoardNewsItem, BoardNewsKind, BoardPromptKind, BoardQueueItem, BoardSession,
  BoardStaging, LiveSession, SessionAgeHours,
} from '../../types'
import type { Part } from './work'

const MIN = 60_000
const DAY = 86_400_000
const DELIVERED_KINDS: readonly BoardDeliveredKind[] = ['accept', 'deny', 'discuss', 'info', 'update', 'withdraw']
const PROMPT_KINDS: readonly BoardPromptKind[] = [...DELIVERED_KINDS, 'update_asker']
const KINDS: readonly BoardAnswerKind[] = [...DELIVERED_KINDS, 'read']
// An Accept, Deny or Withdraw closes its question: the pane strikes it, and later lines on that id change nothing.
const CLOSING: readonly BoardAnswerKind[] = ['accept', 'deny', 'withdraw']
const NEWS_KINDS: readonly BoardNewsKind[] = ['info', 'gate', 'todo']

const promptsOf = (raw: unknown): Partial<Record<BoardPromptKind, string>> | undefined => {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const out: Partial<Record<BoardPromptKind, string>> = {}
  for (const kind of PROMPT_KINDS) {
    const text = (raw as Record<string, unknown>)[kind]
    if (typeof text === 'string' && text.trim()) out[kind] = text
  }
  return out
}

const prioritiesOf = (raw: unknown): string | undefined => {
  const items = Array.isArray(raw) ? raw.filter((p): p is string => typeof p === 'string') : typeof raw === 'string' ? [raw] : []
  const line = items.map(p => p.trim()).filter(Boolean).join(' · ')
  return line || undefined
}

const str = (v: unknown) => (typeof v === 'string' && v.trim() ? v.trim() : undefined)

// `news[]`: an item needs an id and a title; anything else in it is optional, an unknown kind counts as info.
const newsOf = (raw: unknown): BoardNewsItem[] => {
  if (!Array.isArray(raw)) return []
  const out: BoardNewsItem[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const n = item as Record<string, unknown>
    const id = str(n.id)
    const title = str(n.title)
    if (!id || !title) continue
    const kind = NEWS_KINDS.includes(n.kind as BoardNewsKind) ? (n.kind as BoardNewsKind) : undefined
    out.push({ id, title, body: str(n.body), ts: str(n.ts), kind })
  }
  return out
}

const obj = (v: unknown) => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : undefined)
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : undefined)

// `staging`: a booking needs a holder, an acceptance an rc; without either the block is left out.
const stagingOf = (raw: unknown): BoardStaging | undefined => {
  const s = obj(raw)
  if (!s) return undefined
  const b = obj(s.booking)
  const a = obj(s.acceptance)
  const holder = str(b?.holder)
  const rc = str(a?.rc)
  if (!holder && !rc) return undefined
  return {
    booking: holder ? { holder, until: str(b?.until), issue: num(b?.issue) } : undefined,
    acceptance: rc ? { rc, opened: str(a?.opened), due: str(a?.due), pastSla: a?.past_sla === true, issue: num(a?.issue) } : undefined,
    slaHours: num(s.sla_hours),
  }
}

// `2026-11-05T14:00Z` → `11-05 14:00 UTC`; anything else as written.
const utcShort = (ts: string | undefined) => {
  const m = ts ? /^\d{4}-(\d\d-\d\d)T(\d\d:\d\d)/.exec(ts) : null
  return m ? `${m[1]} ${m[2]} UTC` : (ts ?? '?')
}

// The pane's staging lines: who holds staging until when (a booking whose `until` is before `now` shows as expired),
// and an acceptance with its due time and past-SLA mark; the hours are the block's own, board.py writes them.
export const stagingLines = (staging: BoardStaging | undefined, now: number): Part[][][] => {
  if (!staging) return []
  const head: Part[] = [{ text: '◇ Staging', bold: true }]
  const out: Part[][][] = []
  if (staging.booking) {
    const b = staging.booking
    const end = b.until ? Date.parse(b.until) : NaN
    out.push([
      head,
      end <= now
        ? [{ text: `booking of ${b.holder} expired ${utcShort(b.until)}`, dim: true }]
        : [{ text: 'booked by ' }, { text: b.holder, bold: true }, { text: ` until ${utcShort(b.until)}` }],
    ])
  }
  if (staging.acceptance) {
    const a = staging.acceptance
    out.push([
      head,
      [{ text: a.rc, bold: true }, { text: ` in acceptance since ${utcShort(a.opened)}` }],
      a.due ? [{ text: `due ${utcShort(a.due)}`, dim: true }] : [],
      a.pastSla
        ? [{ text: staging.slaHours === undefined ? '⚠ past SLA' : `⚠ past ${staging.slaHours} h`, color: 'warning', bold: true }]
        : [],
    ])
  }
  return out
}

// The news the owner has not marked read: an item whose newest line in the answers file is `read` drops out.
export const unreadNews = (news: readonly BoardNewsItem[], answers: Record<string, BoardAnswer>) =>
  news.filter(n => answers[n.id]?.answer !== 'read')

export const parseBoard = (text: string): BoardFile => {
  const raw = JSON.parse(text) as unknown
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('board file is no JSON object')
  const file = raw as Record<string, unknown>
  return {
    updated: typeof file.updated === 'string' ? file.updated : undefined,
    updatedBy: typeof file.updated_by === 'string' ? file.updated_by : undefined,
    queue: Array.isArray(file.owner_queue) ? (file.owner_queue as BoardQueueItem[]) : [],
    sessions: Array.isArray(file.sessions) ? (file.sessions as BoardSession[]) : [],
    priorities: prioritiesOf(file.priorities),
    news: newsOf(file.news),
    notes: str(file.notes),
    answerPrompts: promptsOf(file.answer_prompts),
    staging: stagingOf(file.staging),
    sessionAgeHours: ageHoursOf(file.session_age_hours),
  }
}

// A session line ages grey from 6 h and red, marked stale, from 24 h (docs/board.md § The file);
// the board file's `session_age_hours` moves both, a pair that is not 0 < grey < stale is ignored.
export const SESSION_AGE_HOURS: SessionAgeHours = { grey: 6, stale: 24 }

const ageHoursOf = (raw: unknown): SessionAgeHours | undefined => {
  const h = obj(raw)
  const grey = num(h?.grey)
  const stale = num(h?.stale)
  return grey !== undefined && stale !== undefined && grey > 0 && grey < stale ? { grey, stale } : undefined
}

export type SessionAge = { label: string; level: 'ok' | 'grey' | 'stale' }

// How old a session line is: `updated_at`, else `since`; undefined when it carries neither.
export const sessionAge = (s: BoardSession, now: number, hours: SessionAgeHours = SESSION_AGE_HOURS): SessionAge | undefined => {
  const stamp = str(s.updated_at) ?? str(s.since)
  const at = stamp ? Date.parse(stamp) : NaN
  if (Number.isNaN(at)) return undefined
  const minutes = Math.max(0, Math.floor((now - at) / MIN))
  const h = minutes / 60
  const label = minutes < 60 ? `${minutes} min` : h < 48 ? `${Math.floor(h)} h` : `${Math.floor(h / 24)} d`
  return { label, level: h >= hours.stale ? 'stale' : h >= hours.grey ? 'grey' : 'ok' }
}

// The answers file and the delivery ledger sit beside the board file, named after its stem
// (docs/board.md § Answers): board.json keeps board-answers.jsonl, acme-board.json gets its own.
export const logPathOf = (boardPath: string, kind: string) => {
  const name = boardPath.replace(/^.*\//, '')
  const stem = name.replace(/\.[^.]*$/, '') || name
  return `${boardPath.slice(0, boardPath.length - name.length)}${stem}-${kind}.jsonl`
}
export const answersPathOf = (boardPath: string) => logPathOf(boardPath, 'answers')
export const deliveriesPathOf = (boardPath: string) => logPathOf(boardPath, 'deliveries')

export const isClosed = (answer: BoardAnswer | undefined) => !!answer && CLOSING.includes(answer.answer)

// The newest answer per question id: later lines win, except that an Accept or Deny closes the id and
// keeps its stamp; a line that is no answer is skipped.
export const lastAnswers = (text: string): Record<string, BoardAnswer> => {
  const out: Record<string, BoardAnswer> = {}
  for (const line of text.split('\n')) {
    if (!line.trim()) continue
    try {
      const a = JSON.parse(line) as Partial<BoardAnswer>
      if (typeof a.id === 'string' && isClosed(out[a.id])) continue
      if (typeof a.id === 'string' && KINDS.includes(a.answer as BoardAnswerKind) && typeof a.ts === 'string') {
        out[a.id] = { id: a.id, answer: a.answer as BoardAnswerKind, ts: a.ts, session: a.session ?? null, ...(a.via ? { via: a.via } : {}) }
      }
    } catch {
      // A torn or foreign line: the answers around it still count.
    }
  }
  return out
}

// The answer the pane shows beside a question. Update keeps the question on the board, so its mark
// lapses once the orchestrator rewrote the board after the press; any other answer shows until handled.
export const shownAnswer = (last: BoardAnswer | undefined, updated: string | undefined): BoardAnswer | undefined => {
  if (last?.answer !== 'update' || !updated) return last
  const at = Date.parse(updated)
  return Number.isNaN(at) || at <= Date.parse(last.ts) ? last : undefined
}

// The texts the deliverer sends: per kind to the orchestrator and the asker, `update_asker` to the asker
// on Update; the board's `answer_prompts` replaces a default, `{id}` standing for the question's id.
const DEFAULT_PROMPT: Record<BoardPromptKind, string> = {
  accept: '{id}: proposal accepted',
  deny: '{id}: proposal denied',
  discuss: "{id}: let's talk about it",
  info: '{id}: I need more information',
  update: '{id}: please check whether this question is still current and correctly worded (goal still active? needs an update?)',
  withdraw: '{id}: withdrawn on the board; take its label off the ticket and say so in one comment there',
  update_asker: 'check whether {id} is still current and well worded; re-ask it with a new id or withdraw it',
}

export const answerPrompt = (answer: BoardPromptKind, id: string, own?: Partial<Record<BoardPromptKind, string>>) =>
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
// or a worker inside that profile (a master may run pinned in it or unpinned outside it); always yellow when only the permission mode differs
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

// A group folds into the pane's last line when nothing in it runs or waits: an idle or done master
// with idle or done workers, or nobody at all.
export const isResting = (group: SessionGroup) =>
  [...(group.head ? [group.head] : []), ...group.workers].every(s => lampOf(s.state) === 'quiet')

export type BoardCounts = { masters: number; runs: number; waits: number; quiet: number; ci: number }

// The header's counter: masters by lamp, and every session in CI.
export const countBoard = (sessions: readonly BoardSession[]): BoardCounts => {
  const masters = sessions.filter(s => isMasterOf(s, sessions))
  const lamps = masters.map(s => lampOf(s.state))
  return {
    masters: masters.length,
    runs: lamps.filter(l => l === 'runs').length,
    waits: lamps.filter(l => l === 'waits').length,
    quiet: lamps.filter(l => l !== 'runs' && l !== 'waits').length,
    ci: sessions.filter(s => s.state === 'ci').length,
  }
}

// Lays segments out left to right, a new line where the next would pass `room`; a segment wider than
// the room stands alone on its line, which the pane clips. `gap` spaces between two on one line.
export const pack = <T>(segments: readonly T[], widthOf: (s: T) => number, room: number, gap = 2): T[][] => {
  const lines: T[][] = []
  let used = 0
  for (const s of segments) {
    const w = widthOf(s)
    const line = lines[lines.length - 1]
    if (line && used + gap + w <= room) {
      line.push(s)
      used += gap + w
    } else {
      lines.push([s])
      used = w
    }
  }
  return lines
}

export const clip = (text: string, room: number) => (text.length > room ? `${text.slice(0, Math.max(0, room - 1))}…` : text)
