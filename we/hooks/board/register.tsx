// /board: a pane with the workspace board an orchestrator session keeps (~/.claude/we-state/board.json,
// option boardFile), the live state of each session and a start-mode lamp. Never writes the board file; a
// question's Accept, Deny, Discuss, More info or Update, and a news item's Read, append one line to board-answers.jsonl beside it.
// In the orchestrator's own session the module is also the deliverer of those lines (deliver.ts), pane open or not.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, PluginOptions, Register, RenderChildren } from 'claude-code'

type On = Parameters<Register>[0]

import type {
  BoardAnswerKind, BoardAnswersView, BoardDeliveriesView, BoardDelivery, BoardNewsItem, BoardNewsKind, BoardQueueItem, BoardSession, BoardView,
  BoardWork, FlowPhase, LiveView, WorkNode,
} from '../../types'
import {
  ageDays, answersPathOf, clip, countBoard, deliveriesPathOf, freshness, groupSessions, isClosed, isMasterOf, isResting, lampOf, lastAnswers,
  liveByName, majorityMode, ownName, pack, parseBoard, shownAnswer, sortQueue, stagingLines, startModeOf, unreadNews,
} from './board'
import type { Lamp, Liveness, SessionGroup, StartMode } from './board'
import {
  NOTICE, RESUBMITTED, answerLines, askerText, deliveryLine, isMissed, keyOf, ledgerState, markerRows, noticeMatches, pendingLines, promptTextOf, rowOf,
  storedHits, versionAtLeast,
} from './deliver'
import type { Awaiting, Delivery, Ledger } from './deliver'
import { buildWork, groupKeys, layoutWork, storiesInScope, storyKey, storyPhase, widthOf, workOf } from './work'
import type { Part } from './work'
import { matchesKey } from '../flow/phase'
import { openFlow } from '../flow/register'
import { ALL_PLANS, defaultBranch, git, loadPrs, parsePlanFiles, planGrep } from '../plans/plans'

const PANE = 'we-board'
const DEFAULT_FILE = '~/.claude/we-state/board.json'
const WATCH_MS = 3_000
const REFRESH_MS = 60_000
// The work trees refresh like /flow: every two minutes, one fetch per repo.
const WORK_MS = 120_000

const view = atom({ plugin: 'we', key: 'boardView' } as const, null, { shape: 'board-view-1' })
const live = atom({ plugin: 'we', key: 'boardLive' } as const, null, { shape: 'board-live-1' })
const answers = atom({ plugin: 'we', key: 'boardAnswers' } as const, null, { shape: 'board-answers-1' })
const deliveries = atom({ plugin: 'we', key: 'boardDeliveries' } as const, null, { shape: 'board-deliveries-1' })
const isOpen = atom({ plugin: 'we', key: 'boardOpen' } as const, false)
const isRestOpen = atom({ plugin: 'we', key: 'boardRestOpen' } as const, false)
const isNotesOpen = atom({ plugin: 'we', key: 'boardNotesOpen' } as const, false)
const work = atom({ plugin: 'we', key: 'boardWork' } as const, null, { shape: 'board-work-1' })
// The masters whose work tree is open, by name; every box starts closed.
const workOpen = atom({ plugin: 'we', key: 'boardWorkOpen' } as const, [], { shape: 'board-work-open-1' })

type $ = EngineInterface

const LAMP: Record<Lamp, { glyph: string; color: string; label: string }> = {
  runs: { glyph: '●', color: 'success', label: 'runs' },
  waits: { glyph: '◉', color: 'warning', label: 'waits for the owner' },
  quiet: { glyph: '○', color: 'inactive', label: 'rests' },
  unknown: { glyph: '?', color: 'inactive', label: 'unknown' },
}

const LIVE: Record<Liveness, { label: string; color: string }> = {
  busy: { label: 'busy', color: 'success' },
  waiting: { label: 'waiting', color: 'warning' },
  blocked: { label: 'blocked', color: 'warning' },
  idle: { label: 'idle', color: 'inactive' },
  gone: { label: 'gone', color: 'inactive' },
}

const ANSWER: Record<BoardAnswerKind, { label: string; color: string }> = {
  accept: { label: 'accepted', color: 'success' },
  deny: { label: 'denied', color: 'error' },
  discuss: { label: 'discuss', color: 'warning' },
  info: { label: 'more info asked', color: 'suggestion' },
  update: { label: 'update asked', color: 'suggestion' },
  read: { label: 'read', color: 'inactive' },
}

const NEWS: Record<BoardNewsKind, { glyph: string; color: string }> = {
  info: { glyph: '•', color: 'suggestion' },
  gate: { glyph: '⚑', color: 'error' },
  todo: { glyph: '◉', color: 'warning' },
}

const START: Record<StartMode['level'], string> = { ok: 'success', warn: 'warning', bad: 'error', none: 'inactive' }

const option = (options: PluginOptions, name: string): string | undefined => {
  const value = options[name]
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

// `~/…` and a relative path both count from the home folder.
async function boardPath($: $, file: string) {
  if (file.startsWith('/')) return file
  const home = (await $.env.get('HOME')) ?? ''
  return `${home}/${file.replace(/^~\/?/, '')}`
}

// The file's mtime is the watch: a stat every few seconds, a read only when it moved.
async function loadBoard($: $, file: string, force = false) {
  const path = await boardPath($, file)
  try {
    if (!(await $.fs.exists(path))) {
      const readAt = await $.clock.now()
      await update($, view, () => ({ path, mtimeMs: 0, readAt, isMissing: true }))
      return
    }
    const stat = await $.fs.stat(path)
    const before = await read($, view)
    if (!force && before && before.mtimeMs === stat.mtimeMs && !before.error && !before.isMissing) return
    const board = parseBoard(String(await $.fs.read(path)))
    const next: BoardView = { path, board, mtimeMs: stat.mtimeMs, readAt: await $.clock.now() }
    await update($, view, () => next)
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err)
    const readAt = await $.clock.now()
    await update($, view, v => ({ ...(v ?? { mtimeMs: 0 }), path, readAt, isMissing: false, error }))
  }
}

// The answers file, re-read only when its mtime moved; a missing file is no answer yet.
async function loadAnswers($: $, file: string, force = false) {
  const path = answersPathOf(await boardPath($, file))
  try {
    if (!(await $.fs.exists(path))) {
      const before = await read($, answers)
      if (!before || before.mtimeMs !== 0 || before.path !== path) await update($, answers, () => ({ path, mtimeMs: 0, byId: {} }))
      return
    }
    const stat = await $.fs.stat(path)
    const before = await read($, answers)
    if (!force && before && before.path === path && before.mtimeMs === stat.mtimeMs) return
    const next: BoardAnswersView = { path, mtimeMs: stat.mtimeMs, byId: lastAnswers(String(await $.fs.read(path))) }
    await update($, answers, () => next)
  } catch (err) {
    $.ui.log(`board: answers file ${path}: ${err instanceof Error ? err.message : String(err)}`)
  }
}

// The delivery ledger as the pane shows it, re-read only when its mtime moved.
async function loadDeliveries($: $, file: string, force = false) {
  const path = deliveriesPathOf(await boardPath($, file))
  try {
    if (!(await $.fs.exists(path))) {
      const before = await read($, deliveries)
      if (!before || before.mtimeMs !== 0 || before.path !== path) await update($, deliveries, () => ({ path, mtimeMs: 0, rows: {} }))
      return
    }
    const stat = await $.fs.stat(path)
    const before = await read($, deliveries)
    if (!force && before && before.path === path && before.mtimeMs === stat.mtimeMs) return
    const ledger = ledgerState(String(await $.fs.read(path)))
    const next: BoardDeliveriesView = { path, mtimeMs: stat.mtimeMs, epoch: ledger.epoch, rows: ledger.rows }
    await update($, deliveries, () => next)
  } catch (err) {
    $.ui.log(`board: ledger ${path}: ${err instanceof Error ? err.message : String(err)}`)
  }
}

// The one row a pane writes: per answer a minute old with no ledger row while the orchestrator's session
// does not run (the live column names it gone or not at all), the marker `coordinator not running`.
async function markStale($: $, file: string) {
  try {
    const v = await read($, view)
    const l = await read($, live)
    const coordinator = v?.board?.updatedBy
    if (!coordinator || !v?.path || !l || l.error) return
    if ((liveByName(l.sessions).get(coordinator)?.liveness ?? 'gone') !== 'gone') return
    const ledgerPath = deliveriesPathOf(v.path)
    const ledger = ledgerState((await readText($, ledgerPath)) ?? '')
    const lines = answerLines((await readText($, answersPathOf(v.path))) ?? '')
    const rows = markerRows(lines, ledger, coordinator, await $.clock.now())
    if (rows.length && (await appendRows($, ledgerPath, rows))) await loadDeliveries($, file, true)
  } catch (err) {
    $.ui.log(`board: marker: ${err instanceof Error ? err.message : String(err)}`)
  }
}

// This session's name, from the live column; probed once more when the column does not know it yet.
async function selfName($: $): Promise<string | undefined> {
  const id = await $.session.id()
  const known = ownName((await read($, live))?.sessions ?? [], id)
  if (known) return known
  await probe($)
  return ownName((await read($, live))?.sessions ?? [], id)
}

// A press of Accept, Deny, Discuss, More info, Update or Read: one appended line. The pane sends nothing:
// the deliverer in the orchestrator's session carries the line, at once when that is this session.
async function answerQuestion($: $, file: string, id: string, answer: BoardAnswerKind) {
  try {
    const path = answersPathOf(await boardPath($, file))
    const me = await selfName($)
    const ts = new Date(await $.clock.now()).toISOString()
    const run = await $.process.run(
      ['python3', '-I', `${$.plugin.root}/hooks/board/answer.py`, path, id, answer, ts, ...(me ? [me] : [])],
      { timeoutMs: 10_000 },
    )
    if (run.exitCode !== 0) throw new Error(run.stderr.trim() || `answer.py exit ${run.exitCode}`)
    await loadAnswers($, file, true)
    if (answer !== 'read' && delivery.isOn) $.clock.after(0, () => void deliverTick($, file))
  } catch (err) {
    $.ui.toast(`board: answer ${id} not saved: ${err instanceof Error ? err.message : String(err)}`)
  }
}

// One probe at a time; a caller that needs its result awaits the one in flight.
let probing: Promise<void> | undefined
function probe($: $): Promise<void> {
  probing ??= probeOnce($).finally(() => {
    probing = undefined
  })
  return probing
}

async function probeOnce($: $) {
  try {
    const run = await $.process.run(['python3', '-I', `${$.plugin.root}/hooks/board/probe.py`], { timeoutMs: 25_000 })
    const out = JSON.parse(run.stdout || '{}') as { sessions?: LiveView['sessions']; error?: string }
    const next: LiveView = {
      sessions: out.sessions ?? [],
      at: await $.clock.now(),
      error: run.exitCode !== 0 ? `probe exit ${run.exitCode}` : out.error,
    }
    await update($, live, () => next)
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err)
    await update($, live, v => ({ sessions: v?.sessions ?? [], at: v?.at ?? 0, error }))
  }
}

// ── The deliverer (deliver.ts) ───────────────────────────────────────────────────────────────────
// Runs in every session from session.start on the floor build and acts only in the one whose live
// name is the board's `updated_by`. Its state lives with the module: a restart forgets what waits,
// and the ledger names again what is still owed.
const FLOOR = '2.1.312'
// A session whose name the live column does not know is probed again at most this often.
const NAME_PROBE_MS = 300_000

type Prompts = Parameters<typeof askerText>[1]

const delivery = {
  isOn: false,
  isBusy: false,
  nameAt: Number.NEGATIVE_INFINITY,
  // Prompts submitted and not yet seen stored, oldest first; the keys an asker send holds while it runs.
  awaiting: [] as Awaiting[],
  sending: new Set<string>(),
  // The main loop's turns: when the running one started, and the start of the last one that ended.
  turnStarts: new Map<string, number>(),
  runningSince: undefined as number | undefined,
  lastEndedAt: undefined as number | undefined,
  lastEndedStart: undefined as number | undefined,
}

const isoOf = (ms: number) => new Date(ms).toISOString()
const isInFlight = (key: string) => delivery.sending.has(key) || delivery.awaiting.some(a => a.key === key)

// The awaiting prompts one stored row confirms: taken out at once, so no check counts them lost.
function takeStored(content: readonly { type: string; text?: string }[]): Awaiting[] {
  const hits = storedHits(delivery.awaiting, content)
  const taken = hits.map(i => delivery.awaiting[i]!)
  delivery.awaiting = delivery.awaiting.filter((_, i) => !hits.includes(i))
  return taken
}

async function readText($: $, path: string): Promise<string | undefined> {
  if (!(await $.fs.exists(path))) return undefined
  return String(await $.fs.read(path))
}

// One write through deliveries.py (O_APPEND); a failure is logged and the rows count as unwritten.
async function appendRows($: $, path: string, rows: readonly (BoardDelivery | { epoch: string })[]): Promise<boolean> {
  try {
    const run = await $.process.run(
      ['python3', '-I', `${$.plugin.root}/hooks/board/deliveries.py`, 'append', path, ...rows.map(r => JSON.stringify(r))],
      { timeoutMs: 10_000 },
    )
    if (run.exitCode === 0) return true
    $.ui.log(`board: ledger ${path}: ${run.stderr.trim() || `deliveries.py exit ${run.exitCode}`}`)
  } catch (err) {
    $.ui.log(`board: ledger ${path}: ${err instanceof Error ? err.message : String(err)}`)
  }
  return false
}

// This session as the coordinator: the board, its name and the two files; undefined in any other session.
async function coordinatorOf($: $, file: string) {
  await loadBoard($, file)
  const v = await read($, view)
  const board = v?.board
  if (!board?.updatedBy || !v?.path) return undefined
  const id = await $.session.id()
  let me = ownName((await read($, live))?.sessions ?? [], id)
  const now = await $.clock.now()
  if (!me && now - delivery.nameAt >= NAME_PROBE_MS) {
    delivery.nameAt = now
    await probe($)
    me = ownName((await read($, live))?.sessions ?? [], id)
  }
  if (!me || me !== board.updatedBy) return undefined
  return { board, name: me, ledgerPath: deliveriesPathOf(v.path), answersPath: answersPathOf(v.path) }
}

// Submits a coordinator-side prompt and waits for its row; registered first, as the row may be stored
// before the submit resolves.
async function submitAwaited($: $, ledgerPath: string, d: Delivery, text: string, tries: number) {
  const key = keyOf(d.line.id, d.line.ts, d.role)
  delivery.awaiting.push({ key, delivery: d, text, ledgerPath, submittedAt: await $.clock.now(), tries })
  try {
    await $.prompt.submit({ text, asUser: true })
  } catch (err) {
    $.ui.log(`board: prompt for ${d.line.id} not submitted: ${err instanceof Error ? err.message : String(err)}`)
  }
}

// One recipient of one line: the asker by peer message, a refusal answered with the routing line to
// the coordinator; the coordinator and the routing line by prompt.
async function deliverOne($: $, ledgerPath: string, coordinator: string, d: Delivery, prompts: Prompts) {
  if (d.role !== 'asker') return submitAwaited($, ledgerPath, d, promptTextOf(d, prompts), 1)
  const key = keyOf(d.line.id, d.line.ts, d.role)
  delivery.sending.add(key)
  try {
    let sent: { isDelivered: boolean; reason?: string }
    try {
      sent = await $.session.send({ to: d.to, text: askerText(d.line, prompts) })
    } catch (err) {
      sent = { isDelivered: false, reason: err instanceof Error ? err.message : String(err) }
    }
    const row = rowOf(d, isoOf(await $.clock.now()), sent.isDelivered, sent.isDelivered ? undefined : sent.reason || 'not delivered')
    if (!(await appendRows($, ledgerPath, [row])) || row.delivered) return
    const route: Delivery = { role: 'route', to: coordinator, line: d.line, about: row }
    if (!isInFlight(keyOf(d.line.id, d.line.ts, 'route'))) await submitAwaited($, ledgerPath, route, promptTextOf(route, prompts), 1)
  } finally {
    delivery.sending.delete(key)
  }
}

// A prompt counted lost: submitted once more with a `resubmitted` row, or after the second time a
// refusal row and a toast in this session.
async function settleMissed($: $, a: Awaiting) {
  const now = await $.clock.now()
  if (a.tries < 2) {
    if (await appendRows($, a.ledgerPath, [rowOf(a.delivery, isoOf(now), false, RESUBMITTED)])) {
      await submitAwaited($, a.ledgerPath, a.delivery, a.text, a.tries + 1)
    }
    return
  }
  const reason = 'not stored after a resubmit'
  await appendRows($, a.ledgerPath, [rowOf(a.delivery, isoOf(now), false, reason)])
  $.ui.toast(`board: ${a.delivery.line.id} did not reach this session (${reason})`)
}

async function checkAwaiting($: $) {
  const now = await $.clock.now()
  const missed = delivery.awaiting.filter(a => isMissed(a, now, delivery))
  delivery.awaiting = delivery.awaiting.filter(a => !missed.includes(a))
  for (const a of missed) await settleMissed($, a)
}

async function recordStored($: $, a: Awaiting) {
  await appendRows($, a.ledgerPath, [rowOf(a.delivery, isoOf(await $.clock.now()), true)])
}

// One pass: the epoch on a first start, then every recipient the ledger still owes, then the waits.
async function deliverTick($: $, file: string) {
  if (delivery.isBusy) return
  delivery.isBusy = true
  try {
    const c = await coordinatorOf($, file)
    if (!c) return
    const ledger: Ledger = ledgerState((await readText($, c.ledgerPath)) ?? '')
    if (!ledger.epoch) {
      // A first start (or a ledger with no start row): nothing older than now is ever sent.
      await appendRows($, c.ledgerPath, [{ epoch: isoOf(await $.clock.now()) }])
      return
    }
    const lines = answerLines((await readText($, c.answersPath)) ?? '')
    const askerOf = (id: string) => c.board.queue.find(q => q.id === id)?.session ?? undefined
    for (const d of pendingLines(lines, ledger, c.name, askerOf)) {
      if (!isInFlight(keyOf(d.line.id, d.line.ts, d.role))) await deliverOne($, c.ledgerPath, c.name, d, c.board.answerPrompts)
    }
    await checkAwaiting($)
  } catch (err) {
    $.ui.log(`board: delivery: ${err instanceof Error ? err.message : String(err)}`)
  } finally {
    delivery.isBusy = false
  }
}

// A held notice for one of our asker messages: that row turns `held`, and the coordinator gets the routing line.
async function heldNotice($: $, file: string, text: string) {
  const c = await coordinatorOf($, file)
  if (!c) return
  const ledger = ledgerState((await readText($, c.ledgerPath)) ?? '')
  const hit = noticeMatches(text, ledger)
  const line = hit && answerLines((await readText($, c.answersPath)) ?? '').find(l => l.id === hit.id && l.ts === hit.answer_ts)
  if (!hit || !line) return
  const row: BoardDelivery = { ...hit, ts: isoOf(await $.clock.now()), delivered: false, reason: 'held' }
  if (!(await appendRows($, c.ledgerPath, [row]))) return
  const route: Delivery = { role: 'route', to: c.name, line, about: row }
  if (!isInFlight(keyOf(line.id, line.ts, 'route'))) await submitAwaited($, c.ledgerPath, route, promptTextOf(route, c.board.answerPrompts), 1)
}

// The engine's version against the floor: below it (or unreadable) a toast and a log line, no deliverer.
async function startDelivery($: $, file: string) {
  let version: string | undefined
  try {
    const v = await $.session.version()
    version = v.base ?? v.version
  } catch {
    version = undefined
  }
  if (!versionAtLeast(version, FLOOR)) {
    const line = `board: delivery needs Claude Code ≥ ${FLOOR}, this is ${version ?? 'an older build'}`
    $.ui.log(line)
    $.ui.toast(line)
    return
  }
  delivery.isOn = true
  $.clock.after(0, () => void deliverTick($, file))
  $.clock.every(WATCH_MS, () => void deliverTick($, file))
}

const fetchedAt = new Map<string, number>()
let isLoadingWork = false
let pendingWork: Set<string> | undefined
// A Refresh pressed while a load runs keeps its fetch for the re-run.
let pendingFresh = false

const textLines = (out: string) => out.split('\n').map(l => l.trim()).filter(Boolean)

// The trees of the boxes in one repo: one fetch (none when the last is younger than the refresh), one
// grep over every plan file on the default branch, the stories' PRs, and branches only for a story
// without a PR.
async function deriveWork($: $, cwd: string, keySets: string[][], fresh: boolean): Promise<WorkNode[][]> {
  const now = await $.clock.now()
  const last = fetchedAt.get(cwd)
  if (fresh || last === undefined || now - last >= WORK_MS - 5_000) {
    await git($, cwd, ['fetch', 'origin', '--quiet'], 60_000)
    fetchedAt.set(cwd, now)
  }
  const base = await defaultBranch($, cwd)
  const files = parsePlanFiles(await git($, cwd, planGrep(base, ALL_PLANS)))
  const storyKeys = storiesInScope([...new Set(keySets.flat())], files)
  const prs = storyKeys.length ? await loadPrs($, cwd, storyKeys) : []
  const bare = storyKeys.filter(k => !prs.some(pr => matchesKey(pr.headRefName, k) || matchesKey(pr.title, k)))
  const refs = bare.length ? textLines(await git($, cwd, ['for-each-ref', '--format=%(refname:short)', 'refs/heads', 'refs/remotes/origin'])) : []
  const phases: Record<string, FlowPhase> = {}
  for (const key of storyKeys) {
    const ahead: string[] = []
    for (const ref of bare.includes(key) ? refs.filter(r => matchesKey(r, key) && r !== 'origin/HEAD') : []) {
      if (Number((await git($, cwd, ['rev-list', '--count', `${base}..${ref}`])).trim()) > 0) ahead.push(ref)
    }
    phases[key] = storyPhase(key, files.find(f => f.kind === 'story' && storyKey(f) === key), prs, ahead)
  }
  return keySets.map(keys => buildWork(keys, files, phases))
}

// Derives the trees of the open boxes (or of `names`), grouped by the repo their master runs in. A
// box whose master carries `work` on the board needs nothing; one without `cwd` says so.
async function loadWork($: $, names?: string[], fresh = false) {
  if (isLoadingWork) {
    pendingWork ??= new Set()
    for (const n of names ?? (await read($, workOpen))) pendingWork.add(n)
    pendingFresh ||= fresh
    return
  }
  isLoadingWork = true
  try {
    const board = (await read($, view))?.board
    const wanted = names ?? (await read($, workOpen))
    if (!board || !wanted.length) return
    const byRepo = new Map<string, SessionGroup[]>()
    const noCwd: string[] = []
    for (const g of groupSessions(board.sessions)) {
      if (!g.head || !wanted.includes(g.head.name) || workOf(g.head.work) || !groupKeys(g).length) continue
      if (!g.head.cwd) noCwd.push(g.head.name)
      else byRepo.set(g.head.cwd, [...(byRepo.get(g.head.cwd) ?? []), g])
    }
    const at = await $.clock.now()
    const set = (name: string, next: (was: BoardWork | undefined) => BoardWork) =>
      update($, work, v => ({ ...(v ?? {}), [name]: next(v?.[name]) }))
    for (const name of noCwd) await set(name, () => ({ nodes: [], at, error: 'no cwd on the board' }))
    for (const [cwd, groups] of byRepo) {
      for (const g of groups) await set(g.head!.name, was => ({ nodes: was?.nodes ?? [], at: was?.at ?? 0, isLoading: true }))
      try {
        const trees = await deriveWork($, cwd, groups.map(groupKeys), fresh)
        const done = await $.clock.now()
        for (const [i, g] of groups.entries()) await set(g.head!.name, () => ({ nodes: trees[i] ?? [], at: done }))
      } catch (err) {
        const error = err instanceof Error ? err.message : String(err)
        $.ui.log(`board: work tree in ${cwd}: ${error}`)
        for (const g of groups) await set(g.head!.name, was => ({ nodes: was?.nodes ?? [], at: was?.at ?? 0, error }))
      }
    }
  } finally {
    isLoadingWork = false
    const next = pendingWork
    const nextFresh = pendingFresh
    pendingWork = undefined
    pendingFresh = false
    if (next?.size) $.clock.after(0, () => void loadWork($, [...next], nextFresh))
  }
}

// A press of a box's Work toggle; opening a box whose tree is missing or older than the refresh derives it.
async function toggleWork($: $, name: string) {
  const open = await read($, workOpen)
  const isOpening = !open.includes(name)
  await update($, workOpen, () => (isOpening ? [...open, name] : open.filter(n => n !== name)))
  if (!isOpening) return
  const was = (await read($, work))?.[name]
  if (!was || was.error || (await $.clock.now()) - was.at >= WORK_MS) $.clock.after(0, () => void loadWork($, [name]))
}

const fileOf = (options: PluginOptions) => option(options, 'boardFile') ?? DEFAULT_FILE

function refreshAll($: $, file: string) {
  $.clock.after(0, () => {
    void loadBoard($, file, true)
    void loadAnswers($, file, true)
    void loadDeliveries($, file, true)
    void probe($).then(() => markStale($, file))
    void loadWork($, undefined, true)
  })
}

// /board's work, also the flow pane's Board button: a plugin's own $.command.run does not reach its own hook.
export async function openBoard($: $, options: PluginOptions): Promise<string> {
  await update($, isOpen, () => true)
  const opened = await $.ui.open({ id: PANE, title: 'Board' })
  refreshAll($, fileOf(options))
  return opened.isPlaced ? 'Board pane opened.' : `Board pane waits undrawn: ${opened.reason}`
}

// Run from the module's one session.start hook (hooks/register.ts); everything it reaches with $
// is a function declaration, the only form the engine follows past an import.
export async function startBoard($: $, options: PluginOptions) {
  const file = fileOf(options)
  await $.command.register({ name: 'board', description: 'Workspace board: who works on what and what waits for the owner' })
  // The deliverer runs from here, pane or not; the pane's own timers read only once /board was opened.
  await startDelivery($, file)
  $.clock.every(WATCH_MS, () => {
    void read($, isOpen).then(open => {
      if (!open) return
      void loadBoard($, file)
      void loadAnswers($, file)
      void loadDeliveries($, file)
    })
  })
  $.clock.every(REFRESH_MS, () => {
    void read($, isOpen).then(open => {
      if (!open) return
      void loadBoard($, file, true)
      void loadAnswers($, file, true)
      void loadDeliveries($, file, true)
      void probe($).then(() => markStale($, file))
    })
  })
  $.clock.every(WORK_MS, () => {
    void read($, isOpen).then(open => {
      if (open) void loadWork($)
    })
  })
  if (await read($, isOpen)) void $.ui.open({ id: PANE, title: 'Board' })
  else if (await autoOpens($, options)) await openBoard($, options)
}

// Option boardAutoOpen: `on` opens /board in every session, `orchestrator` only in the session whose
// pin holds the crew's coordinator role (crew.py is-role reads the session's environment), else off.
async function autoOpens($: $, options: PluginOptions): Promise<boolean> {
  const mode = option(options, 'boardAutoOpen')
  if (mode === 'on') return true
  if (mode !== 'orchestrator') return false
  try {
    const session = await $.session.id()
    const run = await $.process.run(['python3', '-I', `${$.plugin.root}/scripts/crew.py`, 'is-role', 'coordinator', '--session', session], { timeoutMs: 10_000 })
    return run.exitCode === 0
  } catch {
    return false
  }
}

export const registerBoard = (on: On, options: PluginOptions) => {
  const file = fileOf(options)
  const masterProfile = option(options, 'masterProfile')

  on('command.run', { command: 'board' }, async $ => ({ text: await openBoard($, options) }))

  // The deliverer's carriers: a stored user row confirms a submitted prompt, a held notice refuses an
  // asker message, and the main loop's turns time a prompt that never shows.
  on('session.append', async ($, e, next) => {
    const stored = await next(e)
    if (delivery.awaiting.length && e.agentId === undefined && e.message.type === 'user') {
      for (const hit of takeStored(e.message.content)) $.clock.after(0, () => void recordStored($, hit))
    }
    return stored
  }).catch(($, e, next) => next(e))
  on('session.receive', ($, e, next) => {
    if (delivery.isOn && e.text.includes(NOTICE)) $.clock.after(0, () => void heldNotice($, file, e.text))
    return next(e)
  }).catch(($, e, next) => next(e))
  on('turn.start', async ($, e, next) => {
    if (delivery.isOn && e.agentId === undefined) {
      const now = await $.clock.now()
      delivery.turnStarts.set(e.turnId, now)
      delivery.runningSince = now
    }
    return next(e)
  })
  on('turn.complete', async ($, e, next) => {
    if (delivery.isOn && e.agentId === undefined) {
      const started = delivery.turnStarts.get(e.turnId)
      delivery.turnStarts.delete(e.turnId)
      delivery.runningSince = undefined
      delivery.lastEndedAt = await $.clock.now()
      if (started !== undefined) delivery.lastEndedStart = started
      if (delivery.awaiting.length) $.clock.after(0, () => void checkAwaiting($))
    }
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const v = await read($, view)
    const l = await read($, live)
    const given = (await read($, answers))?.byId ?? {}
    const ledgerRows = (await read($, deliveries))?.rows ?? {}
    const restOpen = await read($, isRestOpen)
    const notesOpen = await read($, isNotesOpen)
    const opened = await read($, workOpen)
    const trees = (await read($, work)) ?? {}
    const now = await $.clock.now()
    const width = Math.max(30, e.props.bodyColumns ?? e.viewport?.columns ?? 80)
    // Inside a frame: the border and one column of padding on each side.
    const inner = width - 4

    if (!v) return <Text dimColor>{`reading ${file} …`}</Text>

    const board = v.board
    const fresh = freshness(board?.updated, now)
    const freshColor = fresh?.level === 'stale' ? 'error' : fresh?.level === 'warn' ? 'warning' : undefined
    const sessions = board?.sessions ?? []
    const liveMap = l ? liveByName(l.sessions) : undefined
    const majority = l ? majorityMode(l.sessions) : undefined
    const onBoard = new Set(sessions.map(s => s.name))
    const offBoard = l ? [...new Set(l.sessions.map(s => s.name).filter((n): n is string => !!n && !onBoard.has(n)))] : []

    // Segments packed into lines no wider than `room`; a segment wider than the room is clipped.
    const textLine = (line: Part[][], room: number, key: string, sep = '  ') => (
      <Text key={key}>
        {line.flatMap((seg, j) => {
          let left = room - (j ? sep.length : 0)
          return [
            ...(j ? [<Text key={`${j}-gap`} dimColor>{sep}</Text>] : []),
            ...seg.map((p, k) => {
              const text = clip(p.text, Math.max(0, left))
              left -= text.length
              return <Text key={`${j}-${k}`} color={p.color} bold={p.bold} dimColor={p.dim}>{text}</Text>
            }),
          ]
        })}
      </Text>
    )
    const lines = (segs: Part[][], room: number, key: string, sep = '  ') =>
      pack(segs.filter(seg => widthOf(seg) > 0), widthOf, room, sep.length).map((line, i) => textLine(line, room, `${key}-${i}`, sep))

    const frame = (key: string, color: string | undefined, children: RenderChildren[]) => (
      <Box key={key} flexDirection="column" borderStyle="round" borderColor={color} paddingX={1}>{children}</Box>
    )

    // An Accept or Deny strikes the card at once: dim, the question struck through, no buttons, the
    // stamp and the delivery line kept, whatever the board file still lists.
    const queueCard = (q: BoardQueueItem, i: number) => {
      const days = ageDays(q.since ?? undefined, now)
      const last = q.id ? shownAnswer(given[q.id], board?.updated) : undefined
      const struck = isClosed(last)
      const delivered = deliveryLine(last, ledgerRows, board?.updatedBy)
      const press = (answer: BoardAnswerKind) => () => {
        if (q.id) void answerQuestion($, file, q.id, answer)
      }
      const head: Part[][] = [
        q.id ? [{ text: q.id, bold: !struck, dim: struck }] : [],
        days !== undefined
          ? [{ text: days === 0 ? 'today' : `${days} d`, color: struck ? undefined : days >= 7 ? 'error' : days >= 2 ? 'warning' : undefined, bold: !struck && days >= 2, dim: struck }]
          : [],
        q.session ? [{ text: q.session, dim: struck }] : [],
        q.key ? [{ text: q.key, dim: true }] : [],
      ]
      const buttons = q.id && !struck
        ? [
            ...(q.recommendation ? [{ key: `accept-${q.id}`, label: 'Accept', on: press('accept') }] : []),
            { key: `deny-${q.id}`, label: 'Deny', on: press('deny') },
            { key: `discuss-${q.id}`, label: 'Discuss', on: press('discuss') },
            { key: `info-${q.id}`, label: 'More info', on: press('info') },
            { key: `update-${q.id}`, label: 'Update', on: press('update') },
          ]
        : []
      const answered = last
        ? `✓ ${ANSWER[last.answer].label} ${last.ts.slice(11, 16)} UTC${last.session ? ` (${last.session})` : ''}`
        : undefined
      // Buttons and the last answer share a row while they fit; the answer moves under them when not.
      const row = [...buttons.map(b => ({ ...b, width: b.label.length + 4 })), ...(answered ? [{ key: 'answered', label: answered, width: answered.length }] : [])]
      return (
        <Box key={`q-${q.id ?? i}`} flexDirection="column" marginTop={i ? 1 : 0}>
          {lines(head, inner, `q-${i}-head`)}
          {q.ask && <Text dimColor={struck} strikethrough={struck}>{q.ask}</Text>}
          {q.recommendation && !struck && <Text color="suggestion">{`→ ${q.recommendation}`}</Text>}
          {pack(row, r => r.width, inner, 1).map((line, j) => (
            <Box key={`q-${i}-row-${j}`} flexDirection="row" gap={1}>
              {line.map(r =>
                'on' in r ? (
                  <Button key={r.key} label={r.label} onPress={r.on} />
                ) : (
                  <Text key={`answered-${q.id}`} color={last ? ANSWER[last.answer].color : undefined}>{clip(r.label, inner)}</Text>
                ),
              )}
            </Box>
          ))}
          {delivered && (
            <Text key={`delivery-${q.id}`} color={delivered.isDelivered ? 'inactive' : 'warning'}>{clip(delivered.text, inner)}</Text>
          )}
        </Box>
      )
    }

    // One news item on one line: Read first so the buttons form a column, then kind glyph, bold title cut
    // to the line and its age; the body dimmed and indented under it. No blank line between items.
    const newsItem = (n: BoardNewsItem) => {
      const kind = NEWS[n.kind ?? 'info']
      const days = ageDays(n.ts, now)
      const age = days === undefined ? '' : days === 0 ? 'today' : `${days} d`
      const read = { label: 'Read', width: 8 }
      const room = inner - read.width - 1
      const parts: Part[] = [{ text: `${kind.glyph} `, color: kind.color, bold: true }]
      const ageRoom = age ? age.length + 2 : 0
      parts.push({ text: clip(n.title, Math.max(8, room - widthOf(parts) - ageRoom)), bold: true })
      if (age) parts.push({ text: `  ${age}`, dim: true })
      return (
        <Box key={`n-${n.id}`} flexDirection="column">
          <Box flexDirection="row" gap={1}>
            <Button key={`read-${n.id}`} label={read.label} onPress={() => void answerQuestion($, file, n.id, 'read')} />
            {textLine([parts], room, 't')}
          </Box>
          {n.body ? <Box paddingLeft={read.width + 3}><Text dimColor>{n.body}</Text></Box> : null}
        </Box>
      )
    }

    const verdictOf = (s: BoardSession) => {
      const one = liveMap?.get(s.name)
      const liveness: Liveness | undefined = liveMap ? one?.liveness ?? 'gone' : undefined
      return { lamp: LAMP[lampOf(s.state)], liveness, start: startModeOf(s, isMasterOf(s, sessions), one, majority, masterProfile) }
    }

    const startReason = (start: StartMode, key: string, indent = 0) =>
      start.level === 'bad' || start.level === 'warn' ? (
        <Box key={key} paddingLeft={indent}><Text color={START[start.level]}>{start.reason}</Text></Box>
      ) : null

    // A worker in its master's frame: lamp, name, key, PR, live status, start lamp, and what it does, cut to the line.
    const workerLine = (w: BoardSession) => {
      const { lamp, liveness, start } = verdictOf(w)
      const keys = (w.keys ?? []).filter(Boolean).join(' ')
      const parts: Part[] = [
        { text: '└ ', dim: true },
        { text: lamp.glyph, color: lamp.color, bold: true },
        { text: ` ${w.name}`, bold: true },
        ...(keys ? [{ text: `  ${keys}`, dim: true }] : []),
        ...(typeof w.pr === 'number' ? [{ text: `  #${w.pr}`, color: 'suggestion' }] : []),
        ...(liveness ? [{ text: `  ${LIVE[liveness].label}`, color: LIVE[liveness].color }] : []),
        ...(start.level !== 'none' ? [{ text: '  ●', color: START[start.level] }] : []),
      ]
      const room = inner - widthOf(parts) - 2
      if (w.now && room >= 8) parts.push({ text: `  ${clip(w.now, room)}`, dim: true })
      return (
        <Box key={`w-${w.name}`} flexDirection="column">
          {lines([parts], inner, `w-${w.name}`)}
          {startReason(start, `w-${w.name}-start`, 4)}
          {w.note && <Box paddingLeft={4}><Text color="warning">{`⚠ ${w.note}`}</Text></Box>}
        </Box>
      )
    }

    const groupFrame = (group: SessionGroup, i: number) => {
      if (!group.head) {
        return frame(`g-rest-${i}`, 'inactive', [
          <Text key="t" dimColor>— no master —</Text>,
          ...group.workers.map(workerLine),
        ])
      }
      const s = group.head
      const { lamp, liveness, start } = verdictOf(s)
      const keys = (s.keys ?? []).filter(Boolean)
      const title: Part[][] = [
        [{ text: lamp.glyph, color: lamp.color, bold: true }, { text: ` ${s.name}`, bold: true }],
        s.companion ? [{ text: `[${s.companion}]`, color: 'claude' }] : [],
        keys.length ? [{ text: keys.join(' '), dim: true }] : [],
        typeof s.pr === 'number' ? [{ text: `#${s.pr}`, color: 'suggestion' }] : [],
        liveness ? [{ text: LIVE[liveness].label, color: LIVE[liveness].color }] : [],
        start.level !== 'none' ? [{ text: `● ${start.mode ?? '?'}`, color: START[start.level] }] : [],
        // A bare priority rides in the title; with a direction it leads that line.
        typeof s.priority === 'number' && !s.direction ? [{ text: `P${s.priority}`, dim: true }] : [],
      ]
      // The Work toggle rides last in the title, on the line where it fits.
      const own = workOf(s.work)
      const hasWork = !!own?.length || groupKeys(group).length > 0
      const isWorkOpen = hasWork && opened.includes(s.name)
      const toggle = { label: `${isWorkOpen ? '▾' : '▸'} Work`, width: 10 }
      type TitleSeg = Part[] | typeof toggle
      const titleLines = pack<TitleSeg>(
        [...title.filter(seg => widthOf(seg) > 0), ...(hasWork ? [toggle] : [])],
        seg => ('label' in seg ? seg.width : widthOf(seg)),
        inner,
      ).map((line, i) => {
        const segs = line.filter((seg): seg is Part[] => !('label' in seg))
        if (segs.length === line.length) return textLine(segs, inner, `g-${s.name}-title-${i}`)
        const room = inner - toggle.width - (segs.length ? 2 : 0)
        return (
          <Box key={`g-${s.name}-title-${i}`} flexDirection="row" gap={2}>
            {segs.length ? textLine(segs, room, 't') : null}
            <Button key={`work-${s.name}`} label={toggle.label} onPress={() => void toggleWork($, s.name)} />
          </Box>
        )
      })
      const tree = isWorkOpen ? trees[s.name] : undefined
      const nodes = own ?? tree?.nodes ?? []
      const workBox = isWorkOpen ? (
        <Box key="work" flexDirection="column">
          {layoutWork(nodes, inner).map((line, i) => (
            <Box key={`g-${s.name}-work-${i}`} paddingLeft={2 * line.depth}>{textLine([line.parts], inner - 2 * line.depth, 't')}</Box>
          ))}
          {!own && !nodes.length && !tree?.error ? <Text dimColor>reading git and GitHub …</Text> : null}
          {!own && tree?.error ? <Text color="error">{`Work: ${tree.error}`}</Text> : null}
        </Box>
      ) : null
      const steer = s.direction ? [typeof s.priority === 'number' ? `P${s.priority}` : '', s.direction].filter(Boolean).join(' · ') : ''
      return frame(`g-${s.name}`, start.level === 'bad' ? 'error' : lamp.color, [
        ...titleLines,
        startReason(start, `g-${s.name}-start`),
        s.topic ? <Text key="topic" dimColor>{s.topic}</Text> : null,
        s.now ? <Text key="now">{s.now}</Text> : null,
        steer ? <Text key="steer" color="suggestion">{steer}</Text> : null,
        s.note ? <Text key="note" color="warning">{`⚠ ${s.note}`}</Text> : null,
        workBox,
        group.workers.length ? <Box key="workers" flexDirection="column" marginTop={1}>{group.workers.map(workerLine)}</Box> : null,
      ])
    }

    const groups = groupSessions(sessions)
    const working = groups.filter(g => !isResting(g))
    const resting = groups.filter(isResting)
    const restCount = resting.reduce((n, g) => n + (g.head ? 1 : 0) + g.workers.length, 0) + offBoard.length

    const news = board ? unreadNews(board.news, given) : []
    const counts = countBoard(sessions)
    const barWidth = Math.min(20, counts.masters * 4, width - 2)
    const cells = (n: number) => (counts.masters ? Math.round((n / counts.masters) * barWidth) : 0)
    const runCells = cells(counts.runs)
    const waitCells = Math.min(barWidth - runCells, cells(counts.waits))
    const counter: Part[][] = [
      [
        { text: '█'.repeat(runCells), color: LAMP.runs.color },
        { text: '█'.repeat(waitCells), color: LAMP.waits.color },
        { text: '░'.repeat(barWidth - runCells - waitCells), color: 'inactive' },
        { text: `  ${counts.runs + counts.waits}/${counts.masters} masters active`, bold: true },
      ],
      board?.queue.length ? [{ text: `${board.queue.length} waiting for you`, color: 'warning', bold: true }] : [],
      counts.ci ? [{ text: `${counts.ci} in CI` }] : [],
    ]

    const stamp = (at: number) => (at ? new Date(at).toISOString().slice(11, 16) + ' UTC' : '–')
    const stampText = `file ${stamp(v.readAt)} · live ${stamp(l?.at ?? 0)} · watch 3 s, all 1 min`

    return (
      <Box flexDirection="column" width={width}>
        {lines(
          [
            [{ text: '◆ Board', bold: true }],
            fresh ? [{ text: `as of ${fresh.label} ago${board?.updatedBy ? ` (${board.updatedBy})` : ''}`, color: freshColor }] : [],
          ],
          width,
          'head',
        )}
        {counts.masters > 0 && lines(counter, width, 'count', ' · ')}
        {board?.priorities && <Text dimColor>{board.priorities}</Text>}
        {stagingLines(board?.staging).map((segs, i) => lines(segs, width, `staging-${i}`))}
        {news.length > 0 && (
          <Box flexDirection="column" marginTop={1}>
            {frame('news', 'inactive', [
              <Text key="t" bold>{`News (${news.length})`}</Text>,
              <Box key="items" flexDirection="column">{news.map(newsItem)}</Box>,
            ])}
          </Box>
        )}
        {board?.notes && (
          <Box flexDirection="column" marginTop={1}>
            <Box flexDirection="row" gap={2}>
              <Button key="notes" label={`${notesOpen ? '▾' : '▸'} Notes`} onPress={() => void update($, isNotesOpen, open => !open)} />
              {!notesOpen && <Text dimColor>{clip(board.notes.split('\n')[0] ?? '', Math.max(0, width - 13))}</Text>}
            </Box>
            {notesOpen && <Text dimColor>{board.notes}</Text>}
          </Box>
        )}
        {v.isMissing && (
          <Text dimColor>{`No board yet: your orchestrator session writes ${v.path ?? file}; the schema is in ${$.plugin.root}/docs/board.md.`}</Text>
        )}
        {v.error && <Text color="error">{`File: ${v.error}`}</Text>}

        {board && board.queue.length > 0 && (
          <Box flexDirection="column" marginTop={1}>
            {frame('queue', 'warning', [
              <Text key="t" color="warning" bold>{`Waiting for you (${board.queue.length})`}</Text>,
              <Box key="cards" flexDirection="column" marginTop={1}>{sortQueue(board.queue).map(queueCard)}</Box>,
            ])}
          </Box>
        )}

        {working.length > 0 && <Box flexDirection="column" marginTop={1}>{working.map(groupFrame)}</Box>}

        {restCount > 0 && (
          <Box flexDirection="column" marginTop={1}>
            <Box flexDirection="row">
              <Button
                key="rest"
                label={`${restOpen ? '−' : '+'} ${restCount} idle/other`}
                onPress={() => void update($, isRestOpen, open => !open)}
              />
            </Box>
            {restOpen && resting.map(groupFrame)}
            {restOpen && offBoard.length > 0 && <Text dimColor>{`Live, not on the board: ${offBoard.join(', ')}`}</Text>}
          </Box>
        )}
        {l?.error && <Text color="warning">{`Live column: ${l.error}`}</Text>}

        {pack([{ key: 'refresh', width: 11 }, { key: 'flow', width: 8 }, { key: 'stamp', width: stampText.length }], b => b.width, width).map((line, i) => (
          <Box key={`foot-${i}`} flexDirection="row" gap={2} marginTop={i ? 0 : 1}>
            {line.map(b =>
              b.key === 'refresh' ? (
                <Button key="refresh" hotkey="r" label="Refresh" onPress={() => refreshAll($, file)} />
              ) : b.key === 'flow' ? (
                <Button key="flow" label="Flow" onPress={() => void openFlow($, '')} />
              ) : (
                <Text key="stamp" dimColor>{stampText}</Text>
              ),
            )}
          </Box>
        ))}
        {lines(
          [
            [{ text: '●', color: 'success' }, { text: ' runs', dim: true }],
            [{ text: '◉', color: 'warning' }, { text: ' waits for you', dim: true }],
            [{ text: '○', color: 'inactive' }, { text: ' rests', dim: true }],
            [{ text: '? unknown', dim: true }],
            [{ text: 'second ● = start mode', dim: true }],
          ],
          width,
          'legend',
        )}
      </Box>
    )
  })
}
