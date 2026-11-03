// Delivery of the board's answers (docs/board.md § Answers), the pure half: which answer lines still
// owe whom a message, how the ledger folds, which notice means a hold. register.tsx wires the events.
//
// One deliverer, in the coordinator's session (its live name is the board's `updated_by`), carries
// each answer line to two recipients and writes one ledger row per recipient:
//   coordinator  `$.prompt.submit` as the person; delivered once its user row is stored. No row by
//                the end of a turn that started after the submit (or 30 s idle): submit once more,
//                row `resubmitted`; still none: `delivered: false`.
//   asker        `$.session.send`; `isDelivered: false` (no such name, several, gone) or a held notice
//                later: `delivered: false` with the reason, and a routing prompt to the coordinator
//                (role `route`, confirmed like the coordinator's).
// Without a running coordinator a pane writes one marker row per answer older than 60 s; the
// deliverer delivers it anyway, its newer row superseding the marker.
import type { BoardAnswerKind, BoardDeliveredKind, BoardDelivery, BoardDeliveryRole, BoardPromptKind } from '../../types'
import { answerPrompt } from './board'

const DELIVERED: readonly BoardDeliveredKind[] = ['accept', 'deny', 'discuss', 'info', 'update']
const CLOSING: readonly BoardAnswerKind[] = ['accept', 'deny']

// How long a pane waits for any ledger row of an answer before it marks the coordinator not running.
export const MARK_AFTER_MS = 60_000
// How long a submitted prompt may wait in an idle session for its row before it counts as lost.
export const IDLE_MS = 30_000
export const NOT_RUNNING = 'coordinator not running'
export const RESUBMITTED = 'resubmitted'
// A row with one of these reasons is no verdict: the deliverer still carries the line.
const PENDING: readonly string[] = [NOT_RUNNING, RESUBMITTED]

export type AnswerLine = {
  id: string
  answer: BoardDeliveredKind
  ts: string
  session: string | null
  via?: string
  quote?: string
}

const str = (v: unknown) => (typeof v === 'string' && v ? v : undefined)

// The lines a deliverer may carry, in file order. A line whose kind is no delivered kind (Read, a
// legacy free kind) is skipped, as is every line on an id after its first Accept or Deny: that id is
// closed, and a later line on it changes nothing.
export const answerLines = (text: string): AnswerLine[] => {
  const out: AnswerLine[] = []
  const closed = new Set<string>()
  for (const raw of text.split('\n')) {
    if (!raw.trim()) continue
    let a: Record<string, unknown>
    try {
      a = JSON.parse(raw) as Record<string, unknown>
    } catch {
      continue
    }
    if (!a || typeof a !== 'object' || typeof a.id !== 'string' || typeof a.ts !== 'string') continue
    if (closed.has(a.id)) continue
    if (CLOSING.includes(a.answer as BoardAnswerKind)) closed.add(a.id)
    if (!DELIVERED.includes(a.answer as BoardDeliveredKind)) continue
    out.push({
      id: a.id,
      answer: a.answer as BoardDeliveredKind,
      ts: a.ts,
      session: str(a.session) ?? null,
      ...(str(a.via) ? { via: str(a.via) } : {}),
      ...(str(a.quote) ? { quote: str(a.quote) } : {}),
    })
  }
  return out
}

export const keyOf = (id: string, answerTs: string, role: BoardDeliveryRole) => `${id}|${answerTs}|${role}`

export type Ledger = { epoch?: string; rows: Record<string, BoardDelivery> }

const ROLES: readonly BoardDeliveryRole[] = ['coordinator', 'asker', 'route']

// Folds the ledger: per key the row with the newest `ts`, a later line winning a tie, so two equal
// marker rows read as one. The first epoch row is the deliverer's start; a torn line is skipped.
export const ledgerState = (text: string): Ledger => {
  const out: Ledger = { rows: {} }
  for (const raw of text.split('\n')) {
    if (!raw.trim()) continue
    let r: Record<string, unknown>
    try {
      r = JSON.parse(raw) as Record<string, unknown>
    } catch {
      continue
    }
    if (!r || typeof r !== 'object') continue
    if (typeof r.epoch === 'string') {
      out.epoch ??= r.epoch
      continue
    }
    if (typeof r.id !== 'string' || typeof r.answer_ts !== 'string' || typeof r.ts !== 'string') continue
    if (!ROLES.includes(r.role as BoardDeliveryRole) || typeof r.delivered !== 'boolean') continue
    const row = r as unknown as BoardDelivery
    const key = keyOf(row.id, row.answer_ts, row.role)
    const had = out.rows[key]
    if (!had || Date.parse(row.ts) >= Date.parse(had.ts)) out.rows[key] = row
  }
  return out
}

// A verdict: delivered, or refused for a reason the deliverer wrote. A marker or a resubmit is none.
export const isFinal = (row: BoardDelivery | undefined) => !!row && (row.delivered || !PENDING.includes(row.reason ?? ''))

export type Recipient = { role: BoardDeliveryRole; to: string }

// Who a line goes to: the coordinator unless the line came from its own chat; the asker unless the line
// was written in the asker's session. A question no longer on the board, or without `session`, has no asker.
export const recipientsOf = (line: AnswerLine, coordinator: string, asker: string | undefined): Recipient[] => [
  ...(line.via === 'chat' && line.session === coordinator ? [] : [{ role: 'coordinator' as const, to: coordinator }]),
  ...(asker && line.session !== asker ? [{ role: 'asker' as const, to: asker }] : []),
]

const after = (ts: string, epoch: string) => Date.parse(ts) > Date.parse(epoch)

// One recipient of one line; a routing line carries the asker row it reports (`about`).
export type Delivery = Recipient & { line: AnswerLine; about?: BoardDelivery }

// What the deliverer still owes: every recipient of a line newer than the epoch whose key holds no
// verdict, and the coordinator's routing line for an asker refused without one yet. Without an epoch
// nothing is owed: the deliverer writes one first.
export const pendingLines = (
  lines: readonly AnswerLine[],
  ledger: Ledger,
  coordinator: string,
  askerOf: (id: string) => string | undefined,
): Delivery[] => {
  const epoch = ledger.epoch
  if (!epoch) return []
  const owed = (d: Delivery) => !isFinal(ledger.rows[keyOf(d.line.id, d.line.ts, d.role)])
  return lines
    .filter(line => after(line.ts, epoch))
    .flatMap(line => {
      const own: Delivery[] = recipientsOf(line, coordinator, askerOf(line.id)).map(r => ({ ...r, line }))
      const refused = ledger.rows[keyOf(line.id, line.ts, 'asker')]
      const route: Delivery[] = refused && isFinal(refused) && !refused.delivered ? [{ role: 'route', to: coordinator, line, about: refused }] : []
      return [...own, ...route]
    })
    .filter(owed)
}

export const rowOf = (d: Delivery, ts: string, delivered: boolean, reason?: string): BoardDelivery => ({
  id: d.line.id,
  answer_ts: d.line.ts,
  to: d.to,
  role: d.role,
  click_ts: d.line.ts,
  ts,
  delivered,
  ...(reason === undefined ? {} : { reason }),
})

type Prompts = Partial<Record<BoardPromptKind, string>> | undefined

const quoteOf = (line: AnswerLine) => (line.quote ? `\nThe owner's words: "${line.quote}"` : '')

// The prompt the coordinator receives: today's text per kind, the owner's words when the owner gave them.
export const coordinatorText = (line: AnswerLine, prompts: Prompts) => `${answerPrompt(line.answer, line.id, prompts)}${quoteOf(line)}`

// The peer message to the asker: the same answer; for Update, the request to check the question.
export const askerText = (line: AnswerLine, prompts: Prompts) =>
  `${answerPrompt(line.answer === 'update' ? 'update_asker' : line.answer, line.id, prompts)}${quoteOf(line)}`

const oneLine = (reason: string) => reason.replace(/\s+/g, ' ').trim()

// The coordinator's routing line when the asker was not reached.
export const routeText = (line: AnswerLine, asker: string, reason: string) =>
  `${line.id}: the owner's answer (${line.answer}) did not reach ${asker} (${oneLine(reason)}); wake that session or route the answer`

// The text a coordinator-side delivery submits: the answer itself, or the routing line.
export const promptTextOf = (d: Delivery, prompts: Prompts) =>
  d.role === 'route' ? routeText(d.line, d.about?.to ?? '?', d.about?.reason ?? 'not delivered') : coordinatorText(d.line, prompts)

export const NOTICE = '[Cross-session delivery notice]'

// The asker row a held notice names: a delivered asker row whose recipient the notice names, the one
// whose id it quotes first, else the newest. A notice naming no recipient of ours matches nothing.
export const noticeMatches = (text: string, ledger: Ledger): BoardDelivery | undefined => {
  if (!text.includes(NOTICE) || !/\bheld\b/.test(text)) return undefined
  const named = Object.values(ledger.rows).filter(r => r.role === 'asker' && r.delivered && r.to && text.includes(r.to))
  const quoted = named.filter(r => new RegExp(`(^|[^\\w-])${r.id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^\\w-]|$)`).test(text))
  const pool = quoted.length ? quoted : named
  return pool.sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts))[0]
}

// The marker rows a pane writes: per answer newer than the epoch and older than a minute that has no
// row at all while the coordinator does not run. Its `ts` is the click plus a minute, so two panes
// write equal rows; the deliverer's own row is newer and supersedes it.
export const markerRows = (lines: readonly AnswerLine[], ledger: Ledger, coordinator: string, now: number): BoardDelivery[] => {
  const epoch = ledger.epoch
  if (!epoch) return []
  const answered = new Set(Object.values(ledger.rows).map(r => `${r.id}|${r.answer_ts}`))
  return lines
    .filter(l => after(l.ts, epoch) && now - Date.parse(l.ts) >= MARK_AFTER_MS && !answered.has(`${l.id}|${l.ts}`))
    .map(line =>
      rowOf({ line, role: 'coordinator', to: coordinator }, new Date(Date.parse(line.ts) + MARK_AFTER_MS).toISOString(), false, NOT_RUNNING),
    )
}

// `2.1.312` ≥ `2.1.302`: numeric per part; a version that is no release counts as below.
export const versionAtLeast = (version: string | undefined, floor: string) => {
  const parts = (v: string) => v.split('.').map(Number)
  const m = version?.match(/^(\d+\.\d+\.\d+)/)
  if (!m) return false
  const [a, b] = [parts(m[1]!), parts(floor)]
  for (let i = 0; i < 3; i += 1) if (a[i]! !== b[i]!) return a[i]! > b[i]!
  return true
}

// A prompt the deliverer submitted and waits to see stored.
export type Awaiting = { key: string; delivery: Delivery; text: string; ledgerPath: string; submittedAt: number; tries: number }

// The awaiting prompts one stored user row confirms, by index: a text block equal to the prompt, or the
// row's text containing it, as the engine may merge queued prompts into one user message.
export const storedHits = (awaiting: readonly Awaiting[], content: readonly { type: string; text?: string }[]) => {
  const blocks = content.filter(b => b.type === 'text').map(b => (b.text ?? '').trim())
  const whole = blocks.join('\n')
  return awaiting.flatMap((a, i) => {
    const text = a.text.trim()
    return text && (blocks.includes(text) || whole.includes(text)) ? [i] : []
  })
}

// The main loop's turns as the deliverer follows them: when the running one started, when the last one
// ended and when that one had started.
export type TurnClock = { runningSince?: number; lastEndedAt?: number; lastEndedStart?: number }

// Lost: a turn that started after the submit ended without its row, or the session sat idle for
// IDLE_MS since the submit and since its last turn ended, with nothing started.
export const isMissed = (a: Awaiting, now: number, turn: TurnClock) =>
  (turn.lastEndedStart !== undefined && turn.lastEndedStart >= a.submittedAt) ||
  (turn.runningSince === undefined && now - Math.max(a.submittedAt, turn.lastEndedAt ?? 0) >= IDLE_MS)

const SHORT_REASONS: readonly [RegExp, string][] = [
  [/^No agent named .* is reachable/, 'not reachable'],
  [/^\d+ agents are named /, 'name not unique'],
  [/^Failed to send to .*(ended|disconnected)/, 'gone'],
]

const shortReason = (reason: string | undefined) => {
  const first = (reason ?? 'not delivered').split('\n')[0]!.trim()
  const known = SHORT_REASONS.find(([pattern]) => pattern.test(first))
  return known ? known[1] : first.length > 40 ? `${first.slice(0, 39)}…` : first
}

export type DeliveryLine = { text: string; isDelivered: boolean }

const hhmm = (ts: string) => `${ts.slice(11, 16)} UTC`

// The line under a question's answer stamp: where its newest answer went, or with whom it stays.
// A refusal of either recipient wins over a delivery; a resubmit still waits and shows nothing.
export const deliveryLine = (
  answer: { id: string; ts: string } | undefined,
  rows: Record<string, BoardDelivery>,
  coordinator: string | undefined,
): DeliveryLine | undefined => {
  if (!answer) return undefined
  const row = (role: BoardDeliveryRole) => rows[keyOf(answer.id, answer.ts, role)]
  const [asker, own] = [row('asker'), row('coordinator')]
  const withCoordinator = (reason: string | undefined) => ({ text: `not delivered, with ${coordinator ?? 'the orchestrator'} (${shortReason(reason)})`, isDelivered: false })
  if (asker && !asker.delivered && isFinal(asker)) return withCoordinator(asker.reason)
  if (own && !own.delivered && own.reason === NOT_RUNNING) return withCoordinator('not running')
  if (own && !own.delivered && isFinal(own)) return withCoordinator(own.reason)
  const reached = asker?.delivered ? asker : own?.delivered ? own : undefined
  return reached ? { text: `→ delivered to ${reached.to} ${hhmm(reached.ts)}`, isDelivered: true } : undefined
}
