// /board: a pane with the workspace board an orchestrator session keeps (~/.claude/we-state/board.json,
// option boardFile), the live state of each session and a start-mode lamp. Never writes the board file; a
// question's Accept, Discuss or More info appends one line to board-answers.jsonl beside it.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, PluginOptions, Register, RenderChildren } from 'claude-code'

type On = Parameters<Register>[0]

import type { BoardAnswerKind, BoardAnswersView, BoardQueueItem, BoardSession, BoardView, LiveView } from '../../types'
import {
  ageDays, answerPrompt, answersPathOf, clip, countBoard, freshness, groupSessions, isMasterOf, isResting, lampOf, lastAnswers,
  liveByName, majorityMode, ownName, pack, parseBoard, sortQueue, startModeOf,
} from './board'
import type { Lamp, Liveness, SessionGroup, StartMode } from './board'
import { openFlow } from '../flow/register'

const PANE = 'we-board'
const DEFAULT_FILE = '~/.claude/we-state/board.json'
const WATCH_MS = 3_000
const REFRESH_MS = 60_000

const view = atom({ plugin: 'we', key: 'boardView' } as const, null, { shape: 'board-view-1' })
const live = atom({ plugin: 'we', key: 'boardLive' } as const, null, { shape: 'board-live-1' })
const answers = atom({ plugin: 'we', key: 'boardAnswers' } as const, null, { shape: 'board-answers-1' })
const isOpen = atom({ plugin: 'we', key: 'boardOpen' } as const, false)
const isRestOpen = atom({ plugin: 'we', key: 'boardRestOpen' } as const, false)

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
  discuss: { label: 'discuss', color: 'warning' },
  info: { label: 'more info asked', color: 'suggestion' },
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

// This session's name, from the live column; probed once more when the column does not know it yet.
async function selfName($: $): Promise<string | undefined> {
  const id = await $.session.id()
  const known = ownName((await read($, live))?.sessions ?? [], id)
  if (known) return known
  await probe($)
  return ownName((await read($, live))?.sessions ?? [], id)
}

// A press of Accept, Discuss or More info: one appended line, and in the orchestrator's own session
// (its name is the board's `updated_by`) the matching prompt, queued as if the person typed it.
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
    const board = (await read($, view))?.board
    if (me && board?.updatedBy && me === board.updatedBy) {
      await $.prompt.submit({ text: answerPrompt(answer, id, board.answerPrompts), asUser: true })
    }
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

const fileOf = (options: PluginOptions) => option(options, 'boardFile') ?? DEFAULT_FILE

function refreshAll($: $, file: string) {
  $.clock.after(0, () => {
    void loadBoard($, file, true)
    void loadAnswers($, file, true)
    void probe($)
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
  // Timers run only once /board was opened in this session; nothing polls before that.
  $.clock.every(WATCH_MS, () => {
    void read($, isOpen).then(open => {
      if (!open) return
      void loadBoard($, file)
      void loadAnswers($, file)
    })
  })
  $.clock.every(REFRESH_MS, () => {
    void read($, isOpen).then(open => {
      if (!open) return
      void loadBoard($, file, true)
      void loadAnswers($, file, true)
      void probe($)
    })
  })
  if (await read($, isOpen)) void $.ui.open({ id: PANE, title: 'Board' })
}

// A run of text that stays on one line, in parts that colour it.
type Part = { text: string; color?: string; bold?: boolean; dim?: boolean }
const widthOf = (seg: Part[]) => seg.reduce((n, p) => n + p.text.length, 0)

export const registerBoard = (on: On, options: PluginOptions) => {
  const file = fileOf(options)
  const masterProfile = option(options, 'masterProfile')

  on('command.run', { command: 'board' }, async $ => ({ text: await openBoard($, options) }))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const v = await read($, view)
    const l = await read($, live)
    const given = (await read($, answers))?.byId ?? {}
    const restOpen = await read($, isRestOpen)
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
    const lines = (segs: Part[][], room: number, key: string, sep = '  ') =>
      pack(segs.filter(seg => widthOf(seg) > 0), widthOf, room, sep.length).map((line, i) => (
        <Text key={`${key}-${i}`}>
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
      ))

    const frame = (key: string, color: string | undefined, children: RenderChildren[]) => (
      <Box key={key} flexDirection="column" borderStyle="round" borderColor={color} paddingX={1}>{children}</Box>
    )

    const queueCard = (q: BoardQueueItem, i: number) => {
      const days = ageDays(q.since ?? undefined, now)
      const last = q.id ? given[q.id] : undefined
      const press = (answer: BoardAnswerKind) => () => {
        if (q.id) void answerQuestion($, file, q.id, answer)
      }
      const head: Part[][] = [
        q.id ? [{ text: q.id, bold: true }] : [],
        days !== undefined ? [{ text: days === 0 ? 'today' : `${days} d`, color: days >= 7 ? 'error' : days >= 2 ? 'warning' : undefined, bold: days >= 2 }] : [],
        q.session ? [{ text: q.session }] : [],
        q.key ? [{ text: q.key, dim: true }] : [],
      ]
      const buttons = q.id
        ? [
            ...(q.recommendation ? [{ key: `accept-${q.id}`, label: 'Accept', on: press('accept') }] : []),
            { key: `discuss-${q.id}`, label: 'Discuss', on: press('discuss') },
            { key: `info-${q.id}`, label: 'More info', on: press('info') },
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
          {q.ask && <Text>{q.ask}</Text>}
          {q.recommendation && <Text color="suggestion">{`→ ${q.recommendation}`}</Text>}
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

    // A worker in its master's frame: lamp, name, key, PR, start lamp, and what it does, cut to the line.
    const workerLine = (w: BoardSession) => {
      const { lamp, start } = verdictOf(w)
      const keys = (w.keys ?? []).filter(Boolean).join(' ')
      const parts: Part[] = [
        { text: '└ ', dim: true },
        { text: lamp.glyph, color: lamp.color, bold: true },
        { text: ` ${w.name}`, bold: true },
        ...(keys ? [{ text: `  ${keys}`, dim: true }] : []),
        ...(typeof w.pr === 'number' ? [{ text: `  #${w.pr}`, color: 'suggestion' }] : []),
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
      const steer = s.direction ? [typeof s.priority === 'number' ? `P${s.priority}` : '', s.direction].filter(Boolean).join(' · ') : ''
      return frame(`g-${s.name}`, start.level === 'bad' ? 'error' : lamp.color, [
        ...lines(title, inner, `g-${s.name}-title`),
        startReason(start, `g-${s.name}-start`),
        s.topic ? <Text key="topic" dimColor>{s.topic}</Text> : null,
        s.now ? <Text key="now">{s.now}</Text> : null,
        steer ? <Text key="steer" color="suggestion">{steer}</Text> : null,
        s.note ? <Text key="note" color="warning">{`⚠ ${s.note}`}</Text> : null,
        group.workers.length ? <Box key="workers" flexDirection="column" marginTop={1}>{group.workers.map(workerLine)}</Box> : null,
      ])
    }

    const groups = groupSessions(sessions)
    const working = groups.filter(g => !isResting(g))
    const resting = groups.filter(isResting)
    const restCount = resting.reduce((n, g) => n + (g.head ? 1 : 0) + g.workers.length, 0) + offBoard.length

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
        {board?.notes && frame('notes', 'warning', [<Text key="t" color="warning" bold>{`⚑ ${board.notes}`}</Text>])}
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
