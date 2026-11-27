// /flow's section Crew flow: who works, who waits on whom since when, CI queue and run per PR, the
// stories' stages and every gap. It renders the last snapshot `scripts/flow_intervals.py --snapshot`
// wrote (that script owns the fields and the path) and never runs the producer on the render path:
// a snapshot older than 5 min starts one refresh in the background, and the section redraws when
// it lands.
import { atom, read, update } from 'claude-code'
import type { EngineInterface } from 'claude-code'

import type { CrewFlowHead, CrewFlowNow, CrewFlowView } from '../../types'

type $ = EngineInterface

export const STALE_MS = 5 * 60_000
const PATH_TIMEOUT_MS = 10_000
// A 1-day run takes ~7 s plus the CI source; a hung gh ends here, the old snapshot stays.
const REFRESH_TIMEOUT_MS = 180_000
const MAX_NOW = 14
const MAX_STORIES = 8
// A board line's topic or now is free text; one pane line each, cut here.
export const BOARD_TEXT_MAX = 96

export const crewFlow = atom({ plugin: 'we', key: 'flowCrew' } as const, null)

// One run at a time, and at most one per STALE_MS: a producer that writes nothing is not hammered.
const state = { isRefreshing: false, startedAt: Number.NEGATIVE_INFINITY }

type Snapshot = {
  project?: string
  generated_at?: string
  header?: string[]
  now?: CrewFlowNow[]
  ci?: { prs?: { number: number; title?: string; heads?: CrewFlowHead[] }[]; gap?: string }
  gaps?: { reason: string }[]
  page?: string
}

function script($: $): string {
  return `${$.plugin.root}/scripts/flow_intervals.py`
}

async function snapshotPath($: $): Promise<string> {
  const run = await $.process.run(['python3', '-I', script($), '--snapshot-path'], { timeoutMs: PATH_TIMEOUT_MS })
  const path = run.stdout.trim()
  if (run.exitCode !== 0 || !path) throw new Error(`flow_intervals.py --snapshot-path exit ${run.exitCode}`)
  return path
}

function shape(path: string, doc: Snapshot, isRefreshing: boolean): CrewFlowView {
  const ciLine = (doc.header ?? []).find(line => line.startsWith('CI wait:'))
  return {
    path,
    project: doc.project,
    generatedAt: doc.generated_at,
    ciLine,
    now: doc.now ?? [],
    ci: (doc.ci?.prs ?? []).map(pr => ({ number: pr.number, title: pr.title, heads: pr.heads ?? [] })),
    gaps: (doc.gaps ?? []).map(g => g.reason),
    page: doc.page,
    isRefreshing,
  }
}

// One read of the snapshot file; past STALE_MS (or none yet) one background refresh starts.
export async function loadCrewFlow($: $): Promise<void> {
  let path: string | undefined
  try {
    path = await snapshotPath($)
    const has = await $.fs.exists(path)
    const doc = has ? (JSON.parse(String(await $.fs.read(path))) as Snapshot) : {}
    const age = doc.generated_at ? (await $.clock.now()) - Date.parse(doc.generated_at) : Number.POSITIVE_INFINITY
    const isStale = !(age <= STALE_MS)
    await update($, crewFlow, () => shape(path as string, doc, state.isRefreshing))
    if (isStale) await refreshLater($)
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err)
    await update($, crewFlow, v => ({ ...(v ?? { now: [], ci: [], gaps: [] }), ...(path ? { path } : {}), error, isRefreshing: state.isRefreshing }))
  }
}

// The producer runs outside the dispatch that asked for it, one run at a time.
async function refreshLater($: $) {
  const now = await $.clock.now()
  if (state.isRefreshing || now - state.startedAt < STALE_MS) return
  state.isRefreshing = true
  state.startedAt = now
  await update($, crewFlow, v => (v ? { ...v, isRefreshing: true } : v))
  $.clock.after(0, () => void refreshSnapshot($))
}

async function refreshSnapshot($: $) {
  let error: string | undefined
  try {
    const run = await $.process.run(['python3', '-I', script($), '--since', '1d', '--snapshot'], {
      timeoutMs: REFRESH_TIMEOUT_MS,
    })
    if (run.exitCode !== 0) error = `refresh failed: flow_intervals.py exit ${run.exitCode}; the snapshot shown is the last one`
  } catch (err) {
    error = `refresh failed: ${err instanceof Error ? err.message : String(err)}; the snapshot shown is the last one`
  } finally {
    state.isRefreshing = false
  }
  await loadCrewFlowAfter($, error)
}

async function loadCrewFlowAfter($: $, error?: string) {
  if (!error) return loadCrewFlow($)
  await update($, crewFlow, v => ({ ...(v ?? { now: [], ci: [], gaps: [] }), error, isRefreshing: false }))
}

// `2026-11-20T21:07:00Z` → `21:07`, and how long ago from `now` (ms).
export const since = (iso: string, now: number) => {
  const minutes = Math.max(0, Math.floor((now - Date.parse(iso)) / 60_000))
  const ago = minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} min` : `${minutes} min`
  return `since ${iso.slice(11, 16)} (${ago})`
}

const mins = (seconds: number) => `${Math.round(seconds / 60)} min`

// `ABC-1-build  waits on ci · since 21:07 (12 min)`: one line per lane that is open now.
export const nowLine = (n: CrewFlowNow, now: number) => {
  const what =
    n.kind === 'working'
      ? 'works'
      : n.label
        ? n.label
        : n.kind.startsWith('stage:')
          ? n.kind.slice(6)
          : n.waiting_on
            ? `waits on ${n.waiting_on}`
            : n.kind
  return `${n.who}  ${what}${n.key && n.key !== n.who ? ` (${n.key})` : ''} · ${since(n.since, now)}`
}

// A board line's `topic` or `now` under its session: one indented line, cut with `…`.
export const boardText = (text: string) => {
  const flat = text.replace(/\s+/g, ' ').trim()
  return `    ${flat.length > BOARD_TEXT_MAX ? `${flat.slice(0, BOARD_TEXT_MAX - 1)}…` : flat}`
}

export const ciLine = (number: number, h: CrewFlowHead) =>
  `#${number}  queue ${mins(h.queue_s)} · run ${mins(h.run_s)}${h.open ? ' · still waiting' : ''}`

// The section's lines, top to bottom, as (text, colour) pairs: the render only draws them.
export function crewFlowLines(v: CrewFlowView, now: number): { text: string; color?: string; dim?: boolean; bold?: boolean }[] {
  const out: { text: string; color?: string; dim?: boolean; bold?: boolean }[] = []
  const age = v.generatedAt ? Math.max(0, Math.floor((now - Date.parse(v.generatedAt)) / 60_000)) : undefined
  const stale = age === undefined || age * 60_000 > STALE_MS
  out.push({
    text: `Crew flow${v.project ? ` · ${v.project}` : ''} · ${age === undefined ? 'no snapshot yet' : `snapshot ${age} min old`}${v.isRefreshing ? ' · refreshing…' : ''}`,
    bold: true,
    ...(stale ? { color: 'warning' } : {}),
  })
  const sessions = v.now.filter(n => n.group !== 'stories')
  const working = sessions.filter(n => n.kind === 'working')
  const waiting = sessions.filter(n => n.kind !== 'working')
  for (const n of [...waiting, ...working].slice(0, MAX_NOW)) {
    out.push({ text: nowLine(n, now), ...(n.kind === 'working' ? { color: 'success' } : n.kind.startsWith('waiting:human') ? { color: 'warning' } : {}) })
    // Where the session stands, from its board line: topic, then its own `now`.
    for (const text of [n.topic, n.board_now]) if (text && text.trim()) out.push({ text: boardText(text), dim: true })
  }
  if (sessions.length > MAX_NOW) out.push({ text: `… ${sessions.length - MAX_NOW} more on the page`, dim: true })
  // Stories: the ones waiting on acceptance by name, the other stages counted.
  const stories = v.now.filter(n => n.group === 'stories')
  const review = stories.filter(n => n.kind === 'stage:in_review')
  for (const n of review.slice(0, MAX_STORIES)) out.push({ text: nowLine(n, now), color: 'warning' })
  const counts = new Map<string, number>()
  for (const n of stories) if (n.kind !== 'stage:in_review') counts.set(n.kind.slice(6), (counts.get(n.kind.slice(6)) ?? 0) + 1)
  const rest = review.length > MAX_STORIES ? [`${review.length - MAX_STORIES} more in_review`] : []
  if (counts.size || rest.length) out.push({ text: `stories: ${[...rest, ...[...counts].map(([k, n]) => `${n} ${k}`)].join(' · ')}`, dim: true })
  if (v.ciLine) out.push({ text: v.ciLine, dim: true })
  for (const pr of v.ci) {
    const last = pr.heads[pr.heads.length - 1]
    if (last && (last.open || now - Date.parse(last.end) < 24 * 3_600_000)) out.push({ text: ciLine(pr.number, last) })
  }
  for (const gap of v.gaps) out.push({ text: `gap: ${gap}`, color: 'warning' })
  if (v.error) out.push({ text: v.error, color: 'error' })
  if (v.page) out.push({ text: `Swimlanes: ${v.page}`, dim: true })
  return out
}

export async function readCrewFlow($: $): Promise<CrewFlowView | null> {
  return read($, crewFlow)
}
