// /board: a pane with the workspace board an orchestrator session keeps (~/.claude/we-state/board.json,
// option boardFile), the live state of each session and a start-mode lamp. Reads only; never writes the file.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, PluginOptions, Register } from 'claude-code'

type On = Parameters<Register>[0]

import type { BoardQueueItem, BoardSession, BoardView, LiveView } from '../../types'
import {
  ageDays, freshness, groupSessions, isMasterOf, lampOf, liveByName, majorityMode, parseBoard, sortQueue, startModeOf,
} from './board'
import type { Lamp, Liveness, StartMode } from './board'
import { openFlow } from '../flow/register'

const PANE = 'we-board'
const DEFAULT_FILE = '~/.claude/we-state/board.json'
const WATCH_MS = 3_000
const REFRESH_MS = 60_000

const view = atom({ plugin: 'we', key: 'boardView' } as const, null, { shape: 'board-view-1' })
const live = atom({ plugin: 'we', key: 'boardLive' } as const, null, { shape: 'board-live-1' })
const isOpen = atom({ plugin: 'we', key: 'boardOpen' } as const, false)

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

let isProbing = false
async function probe($: $) {
  if (isProbing) return
  isProbing = true
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
  } finally {
    isProbing = false
  }
}

const fileOf = (options: PluginOptions) => option(options, 'boardFile') ?? DEFAULT_FILE

function refreshAll($: $, file: string) {
  $.clock.after(0, () => {
    void loadBoard($, file, true)
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
    void read($, isOpen).then(open => (open ? loadBoard($, file) : undefined))
  })
  $.clock.every(REFRESH_MS, () => {
    void read($, isOpen).then(open => {
      if (!open) return
      void loadBoard($, file, true)
      void probe($)
    })
  })
  if (await read($, isOpen)) void $.ui.open({ id: PANE, title: 'Board' })
}

export const registerBoard = (on: On, options: PluginOptions) => {
  const file = fileOf(options)
  const masterProfile = option(options, 'masterProfile')

  on('command.run', { command: 'board' }, async $ => ({ text: await openBoard($, options) }))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const v = await read($, view)
    const l = await read($, live)
    const now = await $.clock.now()
    const width = Math.max(30, e.props.bodyColumns ?? e.viewport?.columns ?? 80)

    if (!v) return <Text dimColor>{`reading ${file} …`}</Text>

    const board = v.board
    const fresh = freshness(board?.updated, now)
    const freshColor = fresh?.level === 'stale' ? 'error' : fresh?.level === 'warn' ? 'warning' : undefined
    const sessions = board?.sessions ?? []
    const liveMap = l ? liveByName(l.sessions) : undefined
    const majority = l ? majorityMode(l.sessions) : undefined
    const onBoard = new Set(sessions.map(s => s.name))
    const offBoard = l ? [...new Set(l.sessions.map(s => s.name).filter((n): n is string => !!n && !onBoard.has(n)))] : []

    const queueRow = (q: BoardQueueItem, i: number) => {
      const days = ageDays(q.since ?? undefined, now)
      return (
        <Box key={`q-${q.id ?? i}`} flexDirection="column">
          <Text>
            {days !== undefined && <Text color={days >= 7 ? 'error' : days >= 2 ? 'warning' : undefined} bold>{days === 0 ? 'today' : `${days} d`}</Text>}
            {q.session && <Text bold>{`  ${q.session}`}</Text>}
            {q.key && <Text dimColor>{`  ${q.key}`}</Text>}
          </Text>
          <Box paddingLeft={2} flexDirection="column">
            {q.ask && <Text>{q.ask}</Text>}
            {q.recommendation && <Text color="suggestion">{`→ ${q.recommendation}`}</Text>}
          </Box>
        </Box>
      )
    }

    const sessionRow = (s: BoardSession, isWorker: boolean) => {
      const lamp = LAMP[lampOf(s.state)]
      const one = liveMap?.get(s.name)
      const liveness: Liveness | undefined = liveMap ? one?.liveness ?? 'gone' : undefined
      const start = startModeOf(s, isMasterOf(s, sessions), one, majority, masterProfile)
      const keys = (s.keys ?? []).filter(Boolean)
      return (
        <Box key={`s-${s.name}`} flexDirection="column" paddingLeft={isWorker ? 3 : 0} marginTop={isWorker ? 0 : 1}>
          <Text>
            <Text color={lamp.color} bold>{lamp.glyph}</Text>
            <Text bold>{` ${s.name}`}</Text>
            {s.companion && <Text color="claude">{` [${s.companion}]`}</Text>}
            {keys.length > 0 && <Text dimColor>{`  ${keys.join(' ')}`}</Text>}
            {typeof s.pr === 'number' && <Text color="suggestion">{`  #${s.pr}`}</Text>}
            {liveness && <Text color={LIVE[liveness].color}>{`  ${LIVE[liveness].label}`}</Text>}
            {start.level !== 'none' && <Text color={START[start.level]}>{`  ● ${start.mode ?? '?'}`}</Text>}
          </Text>
          <Box paddingLeft={2} flexDirection="column">
            {start.level === 'bad' || start.level === 'warn' ? <Text color={START[start.level]}>{start.reason}</Text> : null}
            {s.topic && <Text>{s.topic}</Text>}
            {s.now && <Text dimColor>{`now: ${s.now}`}</Text>}
            {(typeof s.priority === 'number' || s.direction) && (
              <Text color="suggestion">
                {typeof s.priority === 'number' ? `P${s.priority}` : ''}
                {typeof s.priority === 'number' && s.direction ? ' · ' : ''}
                {s.direction ?? ''}
              </Text>
            )}
            {s.note && <Text color="warning">{`⚠ ${s.note}`}</Text>}
          </Box>
        </Box>
      )
    }

    const stamp = (at: number) => (at ? new Date(at).toISOString().slice(11, 16) + ' UTC' : '–')

    return (
      <Box flexDirection="column" width={width}>
        <Text>
          <Text bold>◆ Board</Text>
          {fresh && <Text color={freshColor}>{`  as of ${fresh.label} ago${board?.updatedBy ? ` (${board.updatedBy})` : ''}`}</Text>}
        </Text>
        {v.isMissing && (
          <Text dimColor>{`No board yet: your orchestrator session writes ${v.path ?? file}; the schema is in ${$.plugin.root}/docs/board.md.`}</Text>
        )}
        {v.error && <Text color="error">{`File: ${v.error}`}</Text>}

        {board && board.queue.length > 0 && (
          <Box flexDirection="column" marginTop={1}>
            <Text color="warning" bold>{`Waiting for the owner (${board.queue.length})`}</Text>
            {sortQueue(board.queue).map(queueRow)}
          </Box>
        )}

        {groupSessions(sessions).map((group, i) => (
          <Box key={`g-${group.head?.name ?? `rest-${i}`}`} flexDirection="column">
            {!group.head && <Text dimColor>{'\n— no master —'}</Text>}
            {group.head && sessionRow(group.head, false)}
            {group.workers.map(w => sessionRow(w, !!group.head))}
          </Box>
        ))}

        {offBoard.length > 0 && <Text dimColor>{`\nLive, not on the board: ${offBoard.join(', ')}`}</Text>}
        {l?.error && <Text color="warning">{`Live column: ${l.error}`}</Text>}

        <Box flexDirection="row" gap={2} marginTop={1}>
          <Button key="refresh" hotkey="r" label="Refresh" onPress={() => refreshAll($, file)} />
          <Button key="flow" label="Flow" onPress={() => void openFlow($, '')} />
          <Text dimColor>{`file ${stamp(v.readAt)} · live ${stamp(l?.at ?? 0)} · watch 3 s, all 1 min`}</Text>
        </Box>
        <Text dimColor>
          <Text color="success">●</Text>{' runs  '}
          <Text color="warning">◉</Text>{' waits for the owner  '}
          <Text color="inactive">○</Text>{' rests  ? unknown · second ● = start mode'}
        </Text>
      </Box>
    )
  })
}
