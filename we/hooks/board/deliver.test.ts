import { expect, mock, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

import { answerLines, deliveryLine, isFinal, keyOf, ledgerState, markerRows, noticeMatches, versionAtLeast, writerNote } from './deliver'

type T$ = Parameters<TestBody>[0]
type TOn = Parameters<TestBody>[1]

const DIR = '/home/me/.claude/we-state'
const BOARD_PATH = `${DIR}/board.json`
const T0 = Date.parse('2026-11-03T16:00:00Z')
// The deliverer ran before: its start row is an hour old.
const EPOCH = `${JSON.stringify({ epoch: '2026-11-03T15:00:00.000Z' })}\n`

const boardOf = (extra: Record<string, unknown> = {}) =>
  JSON.stringify({
    updated: '2026-11-03T15:00:00Z',
    updated_by: 'coord',
    owner_queue: [
      { id: 'Q1', session: 'asker', key: 'PROJ-40', ask: 'Ship it?', since: '2026-11-03', recommendation: 'yes' },
      { id: 'Q2', session: 'other', key: 'PROJ-41', ask: 'Which one?', since: '2026-11-03', recommendation: '' },
    ],
    sessions: [{ name: 'coord', role: 'master' }],
    ...extra,
  })

const RUN = (stdout: string, exitCode = 0, stderr = '') => ({
  value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false },
})

type Opts = {
  self: { sessionId: string; name: string }
  live?: { name: string; sessionId: string; pid: number | null; status: string }[]
  board?: string
  answers?: string
  ledger?: string
  version?: string
  // What $.session.send answers per recipient; absent means delivered.
  send?: (to: string, text: string) => { isDelivered: true } | { isDelivered: false; reason: string } | Error
  // Whether a submitted prompt is stored as a row (the engine's append); false is the Q189 case.
  stores?: (text: string, n: number) => boolean
  // Whether deliveries.py fails its next append.
  ledgerFails?: () => boolean
  // The session's crew: its resolved board (board.py path), crew.py path and crew.py show.
  crew?: { board: string; show: Record<string, unknown> }
  // A crew whose board.py path fails: crew.py path and show answer, board.py path exits 1.
  show?: Record<string, unknown>
  // What crew.py deliverer prints; '' exits 1 (no role on this machine). Default: the coordinator of `show`.
  deliverer?: string
}

// The default crew.py deliverer of a crew without humans: the coordinator's name, else exit 1.
const delivererOf = (show: Record<string, unknown>) => {
  const crew = show as { roles?: Record<string, string>; members?: Record<string, { name?: string }> }
  const name = crew.roles?.coordinator ? crew.members?.[crew.roles.coordinator]?.name : undefined
  return name ? RUN(`${name}\n`) : RUN('', 1, 'no deliverer')
}

// A fake home: the board, its answers file and the delivery ledger, with answer.py and deliveries.py
// appending as the scripts do, and a session that stores a submitted prompt as a user row.
function home($: T$, on: TOn, o: Opts) {
  const boardPath = o.crew?.board ?? BOARD_PATH
  const ANSWERS = boardPath.replace(/\.json$/, '-answers.jsonl')
  const LEDGER = boardPath.replace(/\.json$/, '-deliveries.jsonl')
  const files = new Map<string, string>([[boardPath, o.board ?? boardOf()]])
  if (o.answers !== undefined) files.set(ANSWERS, o.answers)
  if (o.ledger !== undefined) files.set(LEDGER, o.ledger)
  const mtimes = new Map<string, number>()
  const touch = (path: string) => mtimes.set(path, (mtimes.get(path) ?? 1) + 1)
  const submitted: string[] = []
  const sent: { to: string; text: string }[] = []
  const toasts: string[] = []
  const logs: string[] = []
  let row = 0
  on('env.get', () => ({ value: '/home/me' }))
  on('fs.exists', (_$, e) => ({ value: files.has(String((e as { path?: unknown }).path)) }))
  on('fs.stat', (_$, e) => ({ value: { kind: 'file', size: 1, mtimeMs: mtimes.get(String((e as { path?: unknown }).path)) ?? 1, isLink: false } }))
  on('fs.read', (_$, e) => {
    const path = String((e as { path?: unknown }).path)
    if (!files.has(path)) throw new Error(`ENOENT ${path}`)
    return { value: files.get(path)! }
  })
  on('session.id', () => ({ value: o.self.sessionId }))
  on('session.version', () => ({ value: { version: o.version ?? '2.1.317', base: o.version ?? '2.1.317' } }))
  on('process.run', (_$, e) => {
    const script = String(e.argv[2] ?? '')
    if (script.endsWith('/scripts/board.py')) return o.crew ? RUN(`${o.crew.board}\n`) : RUN('', 1)
    if (script.endsWith('/scripts/crew.py')) {
      const show = o.crew?.show ?? o.show
      if (!show) return RUN('', 1, 'no crew')
      // crew.py path: the crew file in force (the pane resolves its board and live column from it)
      if (e.argv[3] === 'path') return RUN(`${String(show.path ?? '/work/acme/.weside/crew.json')}\n`)
      // crew.py deliverer: the session that delivers on this machine (crew.py owns the rule; test_crew.py)
      if (e.argv[3] === 'deliverer') return o.deliverer !== undefined ? RUN(o.deliverer ? `${o.deliverer}\n` : '', o.deliverer ? 0 : 1) : delivererOf(show)
      return RUN(JSON.stringify(show))
    }
    if (script.endsWith('/answer.py')) {
      const [path, id, answer, ts, session] = e.argv.slice(3)
      files.set(path!, `${files.get(path!) ?? ''}${JSON.stringify({ id, answer, ts, session: session ?? null })}\n`)
      touch(path!)
      return RUN('')
    }
    if (script.endsWith('/deliveries.py')) {
      if (o.ledgerFails?.()) return RUN('', 1, 'deliveries.py: disk full')
      const [verb, path, ...rows] = e.argv.slice(3)
      expect(verb).toBe('append')
      // the real deliveries.py refuses a role it does not know: keep the fake as strict
      for (const r of rows) {
        const role = (JSON.parse(r) as { role?: string }).role
        if (role !== undefined && !['coordinator', 'asker', 'owner', 'route'].includes(role)) {
          return RUN('', 1, `deliveries.py: role must be one of coordinator, asker, owner, route`)
        }
      }
      files.set(path!, `${files.get(path!) ?? ''}${rows.map(r => `${r}\n`).join('')}`)
      touch(path!)
      return RUN('')
    }
    return RUN(JSON.stringify({ sessions: o.live ?? [{ name: o.self.name, sessionId: o.self.sessionId, pid: 9, status: 'idle' }] }))
  })
  on('prompt.submit', async (_$, e) => {
    const text = String((e as { text?: unknown }).text)
    submitted.push(text)
    if (o.stores?.(text, submitted.filter(t => t === text).length) ?? true) {
      row += 1
      await $.session.append({
        message: { type: 'user', role: 'user', content: [{ type: 'text', text }] },
        door: 'prompt',
        origin: { kind: 'plugin', name: 'we', asUser: true },
        uuid: `row-${row}`,
      } as never)
    }
    return { text }
  })
  on('session.send', (_$, e) => {
    const { to, text } = e as { to: string; text: string }
    sent.push({ to, text })
    const r = o.send?.(to, text) ?? { isDelivered: true as const }
    if (r instanceof Error) throw r
    return r
  })
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', (_$, e) => {
    toasts.push(String((e as { text?: unknown }).text))
    return { value: undefined }
  })
  on('ui.log', (_$, e) => {
    logs.push(String((e as { text?: unknown }).text))
    return { value: undefined }
  })
  on('command.register', () => ({ value: { command: 'board' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('session.receive', (_, e) => ({ text: e.text }))
  on('turn.complete', (_, e) => ({ text: e.answer }))
  const ledger = () =>
    (files.get(LEDGER) ?? '')
      .split('\n')
      .filter(Boolean)
      .map(l => JSON.parse(l) as Record<string, unknown>)
  // A line another session's pane (or board.py) appended.
  const click = async (line: Record<string, unknown>) => {
    files.set(ANSWERS, `${files.get(ANSWERS) ?? ''}${JSON.stringify(line)}\n`)
    touch(ANSWERS)
  }
  // The engine storing a prompt that was queued earlier, as its turn begins.
  const store = async (...texts: string[]) => {
    row += 1
    await $.session.append({
      message: { type: 'user', role: 'user', content: texts.map(text => ({ type: 'text', text })) },
      door: 'prompt',
      origin: { kind: 'plugin', name: 'we', asUser: true },
      uuid: `row-${row}`,
    } as never)
  }
  const rows = (id: string, role?: string) => ledger().filter(r => r.id === id && (!role || r.role === role))
  return { files, submitted, sent, toasts, logs, ledger, rows, click, store, answersPath: ANSWERS }
}

const turn = async ($: T$, id: string) => {
  await $.turn.start({ text: '', turnId: id } as never)
  await $.turn.complete({ reason: 'answer', answer: '', durationMs: 1, isAborted: false, turnId: id } as never)
}

const pane = ($: T$) =>
  $.ui.mount({ plugin: 'we', surface: 'terminal', component: 'Pane', requestId: 'we-board', props: { bodyColumns: 80 } as never })

// Q189: the press queued the coordinator's prompt and no user row followed. The deliverer must notice
// at the end of the next turn and submit it once more.
test('a coordinator prompt that is never stored is submitted once more after the next turn (Q189)', async ($, on) => {
  const clock = mock.clock(on, { now: T0 })
  mock.store(on)
  const h = home($, on, { self: { sessionId: 's-coord', name: 'coord' }, ledger: EPOCH, stores: (_text, n) => n > 1 })

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'board', args: '', origin: { kind: 'composer' } } as never)
  await clock.settle()
  const ui = await pane($)
  await ui.press({ key: 'accept-Q1' })
  await clock.advance(3_000)
  await turn($, 't1')
  await clock.advance(3_000)
  expect(h.submitted).toEqual(['Q1: proposal accepted (answered from the board pane in coord)', 'Q1: proposal accepted (answered from the board pane in coord)'])
  await ui.unmount()
})

const iso = (ms: number) => new Date(ms).toISOString()
const NOTICE_TEXT =
  '[Cross-session delivery notice] Your message to asker ("Q1: proposal accepted") was held by that session: NOT delivered: its Claude has not seen it. Do not report it as delivered, do not wait for a reply, and do not resend while held. The usual cause is that the two sessions run in different permission modes: a terminal session then asks its user to approve, but a Claude Desktop or non-interactive session cannot ask, so there the hold expires undelivered unless the modes come to match. A session can also be set to hold every message. Another notice follows on release, denial or expiry. Tell your user what is held and why, or choose another approach.'

// The coordinator's session, started on the floor build with a running ledger.
async function coordinator($: T$, on: TOn, o: Partial<Opts> = {}) {
  const clock = mock.clock(on, { now: T0 })
  mock.store(on)
  const h = home($, on, { self: { sessionId: 's-coord', name: 'coord' }, ledger: EPOCH, ...o })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.settle()
  return { clock, h }
}

const latency = (r: Record<string, unknown>) => Date.parse(String(r.ts)) - Date.parse(String(r.click_ts))

test('a press in another pane reaches the coordinator and the asker within one watch interval', async ($, on) => {
  const { clock, h } = await coordinator($, on)
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(3_000)
  expect(h.submitted).toEqual(['Q1: proposal accepted (answered from the board pane in foxy)'])
  expect(h.sent).toEqual([{ to: 'asker', text: 'Q1: proposal accepted (answered from the board pane in foxy)' }])
  const rows = h.rows('Q1')
  expect(rows.map(r => [r.role, r.to, r.delivered])).toEqual([
    ['asker', 'asker', true],
    ['coordinator', 'coord', true],
  ])
  // click → delivered on the mocked clock: 2 s, the rest of the 3 s watch interval.
  expect(rows.map(latency)).toEqual([2_000, 2_000])
  expect(rows.every(r => r.click_ts === r.answer_ts && r.answer_ts === iso(T0 + 1_000))).toBe(true)
  // The next ticks owe nothing more.
  await clock.advance(9_000)
  expect([h.submitted.length, h.sent.length, h.ledger().length]).toEqual([1, 1, 3])
})

test('a busy coordinator: its row counts when the queued prompt is stored, well within 60 s', async ($, on) => {
  const { clock, h } = await coordinator($, on, { stores: () => false })
  await $.turn.start({ text: 'long work', turnId: 'busy' } as never)
  await h.click({ id: 'Q1', answer: 'discuss', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(42_000)
  // The turn that ran before the submit ends: no resubmit, the prompt is still queued.
  await $.turn.complete({ reason: 'answer', answer: '', durationMs: 43_000, isAborted: false, turnId: 'busy' } as never)
  await clock.advance(1_000)
  expect(h.submitted).toEqual(["Q1: let's talk about it (answered from the board pane in foxy)"])
  await $.turn.start({ text: '', turnId: 'queued' } as never)
  await h.store("Q1: let's talk about it (answered from the board pane in foxy)")
  await clock.settle()
  const row = h.rows('Q1', 'coordinator')[0]!
  expect(row.delivered).toBe(true)
  expect(latency(row)).toBe(42_000)
  expect(latency(row)).toBeLessThanOrEqual(60_000)
})

// The engine merges two prompts queued behind a busy turn into one user row: each is confirmed once,
// whether the row carries them as one joined text or as one block each.
for (const shape of ['one text', 'two blocks'] as const) {
  test(`two prompts stored as one row (${shape}) are each delivered once, none resubmitted`, async ($, on) => {
    const { clock, h } = await coordinator($, on, { stores: () => false })
    await $.turn.start({ text: 'long work', turnId: 'busy' } as never)
    await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
    await h.click({ id: 'Q2', answer: 'discuss', ts: iso(T0 + 1_500), session: 'foxy' })
    await clock.advance(3_000)
    const prompts = ['Q1: proposal accepted (answered from the board pane in foxy)', "Q2: let's talk about it (answered from the board pane in foxy)"]
    expect(h.submitted).toEqual(prompts)
    await $.turn.complete({ reason: 'answer', answer: '', durationMs: 4_000, isAborted: false, turnId: 'busy' } as never)
    await $.turn.start({ text: '', turnId: 'queued' } as never)
    await (shape === 'one text' ? h.store(prompts.join('\n')) : h.store(...prompts))
    await clock.settle()
    await $.turn.complete({ reason: 'answer', answer: '', durationMs: 1, isAborted: false, turnId: 'queued' } as never)
    await clock.advance(9_000)
    expect(h.submitted).toEqual(prompts)
    expect(['Q1', 'Q2'].map(id => h.rows(id, 'coordinator').map(r => r.delivered))).toEqual([[true], [true]])
  })
}

for (const [name, reason] of [
  ['no such name', "No agent named 'asker' is reachable.\nUse ListAgents to see everyone you can message."],
  ['several sessions with the name', "2 agents are named 'asker'. Re-send with the ref of the one you mean:\n  asker [a2ebf0]\n  asker [efd533]"],
  ['a stopped session', "No agent named 'asker' is reachable."],
] as const) {
  test(`an asker refused (${name}) gets a refusal row; the coordinator gets one routing line`, async ($, on) => {
    const { clock, h } = await coordinator($, on, { send: () => ({ isDelivered: false, reason }) })
    await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
    await clock.advance(3_000)
    expect(h.rows('Q1', 'asker')).toEqual([expect.objectContaining({ to: 'asker', delivered: false, reason })])
    const flat = reason.replace(/\s+/g, ' ').trim()
    expect(h.submitted).toEqual(['Q1: proposal accepted (answered from the board pane in foxy)', `Q1: the owner's answer (accept) did not reach asker (${flat}); wake that session or route the answer`])
    expect(h.rows('Q1', 'route')).toEqual([expect.objectContaining({ to: 'coord', delivered: true })])
    await clock.advance(9_000)
    expect([h.sent.length, h.submitted.length]).toEqual([1, 2])
  })
}

test('an answer its asker has not taken 24 h after it is routed to the coordinator', async ($, on) => {
  // Red arm: the deliverer was off past a day; board.py prune waits for the asker or the route row, so the
  // route row is what lets an answered question leave the board, never a silent drop.
  const old = `${JSON.stringify({ epoch: '2026-11-01T00:00:00.000Z' })}\n`
  const { clock, h } = await coordinator($, on, { ledger: old })
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 - 25 * 3600_000), session: 'foxy' })
  await clock.advance(3_000)
  expect(h.rows('Q1', 'route')).toEqual([expect.objectContaining({ to: 'coord', delivered: true })])
  expect(h.submitted).toContain("Q1: the owner's answer (accept) did not reach asker (not reached within 24 h); wake that session or route the answer")
})

test('a fresh answer delivered to its asker routes nothing', async ($, on) => {
  const { clock, h } = await coordinator($, on)
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(3_000)
  expect(h.rows('Q1', 'route')).toHaveLength(0)
})

test('a send that rejects is written as not delivered with its message', async ($, on) => {
  // A test hook that throws is skipped and the kit then rejects the call: the rejection's message is the reason.
  const { clock, h } = await coordinator($, on, { send: () => new Error('socket closed') })
  await h.click({ id: 'Q1', answer: 'deny', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(3_000)
  expect(h.rows('Q1', 'asker')).toEqual([expect.objectContaining({ delivered: false, reason: 'no implementation for session.send' })])
  expect(h.rows('Q1', 'route')).toHaveLength(1)
})

test('a held notice for a delivered asker message turns its row held and routes it', async ($, on) => {
  const { clock, h } = await coordinator($, on)
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(3_000)
  await $.session.receive({ origin: { kind: 'unclassified' }, text: NOTICE_TEXT } as never)
  await clock.settle()
  const asker = h.rows('Q1', 'asker')
  expect(asker.map(r => [r.delivered, r.reason ?? null])).toEqual([
    [true, null],
    [false, 'held'],
  ])
  expect(h.submitted[1]).toBe("Q1: the owner's answer (accept) did not reach asker (held); wake that session or route the answer")
  // A notice naming nobody we sent to changes nothing.
  await $.session.receive({ origin: { kind: 'unclassified' }, text: NOTICE_TEXT.replace('asker', 'stranger').replace('Q1', 'Q9') } as never)
  await clock.settle()
  expect(h.rows('Q1', 'asker')).toHaveLength(2)
})

test('Q189 to the end: no row after the resubmit either is a refusal row and a toast', async ($, on) => {
  const { clock, h } = await coordinator($, on, { stores: () => false })
  await h.click({ id: 'Q1', answer: 'info', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(3_000)
  await turn($, 't1')
  await clock.settle()
  expect(h.rows('Q1', 'coordinator').map(r => r.reason)).toEqual(['resubmitted'])
  await turn($, 't2')
  await clock.settle()
  expect(h.submitted).toEqual(['Q1: I need more information (answered from the board pane in foxy)', 'Q1: I need more information (answered from the board pane in foxy)'])
  expect(h.rows('Q1', 'coordinator').map(r => [r.delivered, r.reason])).toEqual([
    [false, 'resubmitted'],
    [false, 'not stored after a resubmit'],
  ])
  expect(h.toasts).toEqual(['board: Q1 did not reach this session (not stored after a resubmit)'])
  await clock.advance(9_000)
  expect(h.submitted).toHaveLength(2)
})

test('an idle coordinator whose prompt never started a turn resubmits after 30 s', async ($, on) => {
  const { clock, h } = await coordinator($, on, { stores: (_t, n) => n > 1 })
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(3_000)
  await clock.advance(30_000)
  expect(h.submitted).toHaveLength(2)
  expect(h.rows('Q1', 'coordinator').map(r => [r.delivered, r.reason ?? null])).toEqual([
    [false, 'resubmitted'],
    [true, null],
  ])
  expect(latency(h.rows('Q1', 'coordinator')[1]!)).toBeLessThanOrEqual(60_000)
})

test('a ledger present at start: a delivered line is not sent again, a marker line is', async ($, on) => {
  const done = { id: 'Q1', answer_ts: iso(T0 - 600_000), click_ts: iso(T0 - 600_000), ts: iso(T0 - 597_000), delivered: true }
  const marker = {
    id: 'Q2', answer_ts: iso(T0 - 300_000), click_ts: iso(T0 - 300_000), ts: iso(T0 - 240_000), to: 'coord', role: 'coordinator',
    delivered: false, reason: 'coordinator not running',
  }
  const answers = [
    { id: 'Q1', answer: 'accept', ts: iso(T0 - 600_000), session: 'foxy' },
    { id: 'Q2', answer: 'deny', ts: iso(T0 - 300_000), session: 'foxy' },
  ].map(l => `${JSON.stringify(l)}\n`).join('')
  const ledger = EPOCH + [
    { ...done, to: 'coord', role: 'coordinator' },
    { ...done, to: 'asker', role: 'asker' },
    marker,
  ].map(r => `${JSON.stringify(r)}\n`).join('')
  const { clock, h } = await coordinator($, on, { answers, ledger })
  await clock.advance(3_000)
  expect(h.submitted).toEqual(['Q2: proposal denied (answered from the board pane in foxy)'])
  expect(h.sent).toEqual([{ to: 'other', text: 'Q2: proposal denied (answered from the board pane in foxy)' }])
  // The deliverer's newer row supersedes the marker.
  const q2 = h.rows('Q2', 'coordinator')
  expect(q2.map(r => r.delivered)).toEqual([false, true])
})

test('a first start writes the epoch and sends nothing older, legacy lines included', async ($, on) => {
  const answers = [
    { id: 'Q1', answer: 'accept', ts: iso(T0 - 60_000), session: 'foxy' },
    { id: 'Q1', answer: 'decided', ts: '2026-11-02T10:00:00Z', session: 'coord', via: 'chat in coord' },
    { id: 'Q2', answer: 'entfällt', ts: '2026-11-02T10:00:00Z' },
  ].map(l => `${JSON.stringify(l)}\n`).join('') + '{"id":"Q3",\n'
  const { clock, h } = await coordinator($, on, { answers, ledger: undefined })
  await clock.advance(9_000)
  expect(h.ledger()).toEqual([{ epoch: iso(T0) }])
  expect([h.submitted, h.sent, h.logs]).toEqual([[], [], []])
  // A line after the epoch goes out; a later line with a free kind does not.
  await h.click({ id: 'Q2', answer: 'skipped', ts: iso(T0 + 10_000), session: 'foxy' })
  await h.click({ id: 'Q2', answer: 'info', ts: iso(T0 + 11_000), session: 'foxy', via: 'chat in somewhere' })
  await clock.advance(3_000)
  expect(h.submitted).toEqual(['Q2: I need more information (answered from the board pane in foxy)'])
})

test('a line the asker wrote itself goes to the coordinator only', async ($, on) => {
  const { clock, h } = await coordinator($, on)
  await h.click({ id: 'Q1', answer: 'discuss', ts: iso(T0 + 1_000), session: 'asker' })
  await clock.advance(3_000)
  expect([h.submitted, h.sent]).toEqual([["Q1: let's talk about it (answered from the board pane in asker)"], []])
  expect(h.rows('Q1').map(r => r.role)).toEqual(['coordinator'])
})

test('Update asks the asker to check its question and the coordinator as before', async ($, on) => {
  const { clock, h } = await coordinator($, on)
  await h.click({ id: 'Q1', answer: 'update', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(3_000)
  expect(h.sent).toEqual([{ to: 'asker', text: 'check whether Q1 is still current and well worded; re-ask it with a new id or withdraw it (answered from the board pane in foxy)' }])
  expect(h.submitted).toEqual(['Q1: please check whether this question is still current and correctly worded (goal still active? needs an update?) (answered from the board pane in foxy)'])
})

test('a chat answer written back: from the asker\'s chat to the coordinator, from the coordinator\'s chat to the asker', async ($, on) => {
  const { clock, h } = await coordinator($, on)
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'asker', via: 'chat', quote: 'go ahead' })
  await h.click({ id: 'Q2', answer: 'deny', ts: iso(T0 + 1_500), session: 'coord', via: 'chat' })
  await clock.advance(3_000)
  expect(h.submitted).toEqual(['Q1: proposal accepted (answered in the chat of asker)\nThe owner\'s words: "go ahead"'])
  expect(h.sent).toEqual([{ to: 'other', text: 'Q2: proposal denied (answered in the chat of coord)' }])
  expect(h.rows('Q1').map(r => r.role)).toEqual(['coordinator'])
  expect(h.rows('Q2').map(r => r.role)).toEqual(['asker'])
})

test('an Accept or Deny line on a closed id sends nothing', async ($, on) => {
  const { clock, h } = await coordinator($, on)
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(3_000)
  await h.click({ id: 'Q1', answer: 'deny', ts: iso(T0 + 4_000), session: 'foxy' })
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 4_500), session: 'foxy' })
  await clock.advance(6_000)
  expect([h.submitted.length, h.sent.length]).toEqual([1, 1])
})

test('a failed ledger write is logged and the line is carried again on the next tick', async ($, on) => {
  let failures = 1
  const { clock, h } = await coordinator($, on, { send: () => ({ isDelivered: true }), ledgerFails: () => failures-- > 0 })
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'asker' })
  await clock.advance(3_000)
  // The coordinator's row was the failed write: the line stays owed and goes out again.
  expect(h.logs).toEqual([expect.stringContaining('deliveries.py: disk full')])
  await clock.advance(3_000)
  expect(h.rows('Q1', 'coordinator')).toEqual([expect.objectContaining({ delivered: true })])
})

test('a pane in any other session appends the line and delivers nothing', async ($, on) => {
  const clock = mock.clock(on, { now: T0 })
  mock.store(on)
  const h = home($, on, { self: { sessionId: 's-foxy', name: 'foxy' }, ledger: EPOCH })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'board', args: '', origin: { kind: 'composer' } } as never)
  await clock.settle()
  const ui = await pane($)
  await ui.press({ key: 'accept-Q1' })
  await clock.advance(9_000)
  expect(h.files.get(h.answersPath)).toContain('"session":"foxy"')
  expect([h.submitted, h.sent, h.ledger()]).toEqual([[], [], [{ epoch: '2026-11-03T15:00:00.000Z' }]])
  await ui.unmount()
})

test('without a running coordinator a pane marks an answer a minute old, once', async ($, on) => {
  const clock = mock.clock(on, { now: T0 })
  mock.store(on)
  const live = [{ name: 'foxy', sessionId: 's-foxy', pid: 3, status: 'idle' }]
  const h = home($, on, { self: { sessionId: 's-foxy', name: 'foxy' }, ledger: EPOCH, live })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'board', args: '', origin: { kind: 'composer' } } as never)
  await clock.settle()
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(60_000)
  expect(h.ledger()).toHaveLength(1)
  await clock.advance(60_000)
  const marker = { id: 'Q1', answer_ts: iso(T0 + 1_000), to: 'coord', role: 'coordinator', click_ts: iso(T0 + 1_000), ts: iso(T0 + 61_000), delivered: false, reason: 'coordinator not running' }
  expect(h.ledger().slice(1)).toEqual([marker])
  await clock.advance(60_000)
  expect(h.ledger()).toHaveLength(2)
  expect(h.submitted).toEqual([])
})

test('below the floor build: a toast and a log line, no deliverer', async ($, on) => {
  const { clock, h } = await coordinator($, on, { version: '2.1.302' })
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(9_000)
  const line = 'board: delivery needs Claude Code ≥ 2.1.312, this is 2.1.302'
  expect([h.toasts, h.logs]).toEqual([[line], [line]])
  expect([h.submitted, h.sent]).toEqual([[], []])
})

test('two panes marking at once write equal rows; readers fold them to one, a later delivery supersedes', () => {
  const lines = answerLines(`${JSON.stringify({ id: 'Q1', answer: 'accept', ts: iso(T0), session: 'foxy' })}\n`)
  const ledger = ledgerState(EPOCH)
  const [a, b] = [markerRows(lines, ledger, 'coord', T0 + 61_000), markerRows(lines, ledger, 'coord', T0 + 75_000)]
  expect(a).toEqual(b)
  const folded = ledgerState(EPOCH + [...a, ...b].map(r => `${JSON.stringify(r)}\n`).join(''))
  expect(Object.keys(folded.rows)).toEqual([keyOf('Q1', iso(T0), 'coordinator')])
  expect(isFinal(Object.values(folded.rows)[0])).toBe(false)
  const done = { ...a[0]!, ts: iso(T0 + 90_000), delivered: true, reason: undefined }
  const after = ledgerState(`${EPOCH}${JSON.stringify(a[0])}\n${JSON.stringify(done)}\n${JSON.stringify(b[0])}\n`)
  expect(Object.values(after.rows)).toEqual([done])
  // A minute is the bound; nothing is marked without an epoch.
  expect(markerRows(lines, ledger, 'coord', T0 + 59_000)).toEqual([])
  expect(markerRows(lines, ledgerState(''), 'coord', T0 + 61_000)).toEqual([])
})

test('a held notice matches the asker row it names, the quoted id first; other notices match nothing', () => {
  const row = (id: string, ts: string) => ({ id, answer_ts: ts, to: 'asker', role: 'asker', click_ts: ts, ts, delivered: true })
  const ledger = ledgerState([row('Q1', iso(T0)), row('Q7', iso(T0 + 5_000))].map(r => `${JSON.stringify(r)}\n`).join(''))
  expect(noticeMatches(NOTICE_TEXT, ledger)?.id).toBe('Q1')
  expect(noticeMatches(NOTICE_TEXT.replace('("Q1: proposal accepted") ', ''), ledger)?.id).toBe('Q7')
  expect(noticeMatches('[Cross-session delivery notice] 2 of your messages to another session were dropped', ledger)).toBeUndefined()
  expect(noticeMatches(NOTICE_TEXT.replace('[Cross-session delivery notice]', ''), ledger)).toBeUndefined()
})

test('versionAtLeast compares releases part by part; a dev build counts by its release', () => {
  expect(['2.1.312', '2.1.317', '2.2.0', '2.1.312-dev.20260920.t101500.sha1a2b3c4'].map(v => versionAtLeast(v, '2.1.312'))).toEqual([true, true, true, true])
  expect(['2.1.302', '2.0.999', 'dev', undefined].map(v => versionAtLeast(v, '2.1.312'))).toEqual([false, false, false, false])
})

test('deliveryLine: delivered to the asker, else to the coordinator; a refusal or a marker stays with the coordinator', () => {
  const ts = iso(T0)
  const r = (role: string, to: string, delivered: boolean, reason?: string, at = T0 + 2_000) =>
    ({ id: 'Q1', answer_ts: ts, to, role, click_ts: ts, ts: iso(at), delivered, ...(reason ? { reason } : {}) })
  const line = (...rows: ReturnType<typeof r>[]) => deliveryLine({ id: 'Q1', ts }, ledgerState(rows.map(x => `${JSON.stringify(x)}\n`).join('')).rows, 'coord')
  expect(line()).toBeUndefined()
  expect(line(r('asker', 'asker', true), r('coordinator', 'coord', true))).toEqual({ text: '→ delivered to asker 16:00 UTC', isDelivered: true })
  expect(line(r('coordinator', 'coord', true))).toEqual({ text: '→ delivered to coord 16:00 UTC', isDelivered: true })
  expect(line(r('asker', 'asker', false, "2 agents are named 'asker'. Re-send with the ref of the one you mean:\n  asker [a2]"))?.text).toBe('not delivered, with coord (name not unique)')
  expect(line(r('asker', 'asker', true), r('asker', 'asker', false, 'held', T0 + 9_000))?.text).toBe('not delivered, with coord (held)')
  // A session stopped a moment ago, as the live walk answered it.
  const stopped = 'Failed to send to asker: HTTP 409 — that Remote Control session may have ended or disconnected. Call ListAgents to see who is reachable now.'
  expect(line(r('asker', 'asker', false, stopped))?.text).toBe('not delivered, with coord (gone)')
  expect(line(r('asker', 'asker', false, 'x'.repeat(60)))?.text).toBe(`not delivered, with coord (${'x'.repeat(39)}…)`)
  expect(line(r('coordinator', 'coord', false, 'coordinator not running', T0 + 60_000))?.text).toBe('not delivered, with coord (not running)')
  expect(line(r('asker', 'asker', true), r('coordinator', 'coord', false, 'resubmitted'))?.text).toBe('→ delivered to asker 16:00 UTC')
  expect(line(r('coordinator', 'coord', false, 'not stored after a resubmit'))?.text).toBe('not delivered, with coord (not stored after a resubmit)')
})

// Two crews in one HOME: the first keeps board.json with `updated_by` coord; the second
// crew writes its board only through board.py, which never sets `updated_by`. Its coordinator comes
// from its crew file.
const ACME = `${DIR}/acme-board.json`
const acmeCrew = (coordinator = 'ada') => ({
  board: ACME,
  show: {
    path: '/work/acme/.weside/crew.json',
    roles: { coordinator, product: 'bea' },
    members: { ada: { name: 'Ada' }, bea: { name: 'Bea' }, samu: { name: 'coord' } },
    board: { file: '~/.claude/we-state/acme-board.json' },
  },
})
const acmeBoard = (extra: Record<string, unknown> = {}) =>
  JSON.stringify({
    owner_queue: [{ id: 'Q7', session: 'Tess', key: 'PROJ-7', ask: 'Ship it?', since: '2026-11-03', recommendation: 'yes' }],
    sessions: [{ name: 'Ada', role: 'master' }],
    ...extra,
  })

async function crewSession($: T$, on: TOn, name: string, o: Partial<Opts>) {
  const clock = mock.clock(on, { now: T0 })
  mock.store(on)
  const h = home($, on, { self: { sessionId: `s-${name}`, name }, ledger: EPOCH, ...o })
  await $.session.start({ cwd: '/work/acme', surface: 'terminal', isInteractive: true })
  await clock.settle()
  return { clock, h }
}

test('a crew whose board has no updated_by: its coordinator from crew.json delivers from its own files', async ($, on) => {
  const { clock, h } = await crewSession($, on, 'Ada', { crew: acmeCrew(), board: acmeBoard() })
  await h.click({ id: 'Q7', answer: 'accept', ts: iso(T0 + 1_000), session: 'Ada' })
  await clock.advance(3_000)
  expect(h.submitted).toEqual(['Q7: proposal accepted (answered from the board pane in Ada)'])
  expect(h.sent).toEqual([{ to: 'Tess', text: 'Q7: proposal accepted (answered from the board pane in Ada)' }])
  expect(h.rows('Q7').map(r => [r.role, r.to, r.delivered])).toEqual([
    ['asker', 'Tess', true],
    ['coordinator', 'Ada', true],
  ])
  // The first crew's files stay untouched: the ledger is the crew's own.
  expect([...h.files.keys()].filter(k => k.startsWith(`${DIR}/board`))).toEqual([])
  expect(h.files.has(`${DIR}/acme-board-deliveries.jsonl`)).toBe(true)
})

// Several humans: a machine that runs no coordinator delivers through the session crew.py deliverer names
// (its human's first role); before, only the crew's coordinator delivered, so answers read back from a
// ticket on such a machine never reached anyone.
test('a machine without the coordinator delivers through the session crew.py deliverer names', async ($, on) => {
  const { clock, h } = await crewSession($, on, 'Bea', { crew: acmeCrew(), board: acmeBoard(), deliverer: 'Bea' })
  await h.click({ id: 'Q7', answer: 'accept', ts: iso(T0 + 1_000), session: 'Bea' })
  await clock.advance(3_000)
  expect(h.rows('Q7').map(r => [r.role, r.to, r.delivered])).toEqual([
    ['asker', 'Tess', true],
    ['coordinator', 'Bea', true],
  ])
})

test('no deliverer on this machine: nothing is delivered', async ($, on) => {
  const { clock, h } = await crewSession($, on, 'Bea', { crew: acmeCrew(), board: acmeBoard(), deliverer: '' })
  await h.click({ id: 'Q7', answer: 'accept', ts: iso(T0 + 1_000), session: 'Bea' })
  await clock.advance(6_000)
  expect([h.submitted, h.sent, h.rows('Q7')]).toEqual([[], [], []])
})

test('a set updated_by still names the deliverer; the crew coordinator steps in only when it is empty', async ($, on) => {
  const { clock, h } = await crewSession($, on, 'Ada', { crew: acmeCrew(), board: acmeBoard({ updated_by: 'coord' }) })
  await h.click({ id: 'Q7', answer: 'accept', ts: iso(T0 + 1_000), session: 'Ada' })
  await clock.advance(6_000)
  expect([h.submitted, h.sent, h.rows('Q7')]).toEqual([[], [], []])
})

test('a crew without its own board.file does not deliver from the shared board, even with updated_by empty', async ($, on) => {
  const { clock, h } = await crewSession($, on, 'Ada', { show: acmeCrew().show, board: acmeBoard() })
  await h.click({ id: 'Q7', answer: 'accept', ts: iso(T0 + 1_000), session: 'Ada' })
  await clock.advance(6_000)
  expect([h.submitted, h.sent, h.rows('Q7')]).toEqual([[], [], []])
})

test('a crew\'s first deliverer start sends no line older than its epoch', async ($, on) => {
  const answers = `${JSON.stringify({ id: 'Q7', answer: 'accept', ts: iso(T0 - 60_000), session: 'Ada' })}\n`
  const { clock, h } = await crewSession($, on, 'Ada', { crew: acmeCrew(), board: acmeBoard(), answers, ledger: undefined })
  await clock.advance(9_000)
  expect(h.ledger()).toEqual([{ epoch: iso(T0) }])
  expect([h.submitted, h.sent]).toEqual([[], []])
})

// The pane says it out loud (not only in the log) when nobody can deliver, and when presses sit undelivered.
async function paneIn($: T$, on: TOn, o: Partial<Opts>) {
  const clock = mock.clock(on, { now: T0 })
  mock.store(on)
  const live = [{ name: 'foxy', sessionId: 's-foxy', pid: 3, status: 'idle' }]
  const h = home($, on, { self: { sessionId: 's-foxy', name: 'foxy' }, ledger: EPOCH, live, ...o })
  await $.session.start({ cwd: '/work/acme', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'board', args: '', origin: { kind: 'composer' } } as never)
  await clock.settle()
  return { clock, h, ui: await pane($) }
}

test('a board without updated_by in a crew without a coordinator role shows a red no-coordinator line', async ($, on) => {
  const crew = acmeCrew()
  const { ui } = await paneIn($, on, { crew: { ...crew, show: { ...crew.show, roles: { product: 'bea' } } }, board: acmeBoard() })
  expect(await ui.find({ type: 'Text', text: /No coordinator/ })).toBeDefined()
  await ui.unmount()
})

test('a pane press nobody delivered for five minutes shows a red line; a chat line does not count', async ($, on) => {
  const { clock, h, ui } = await paneIn($, on, {})
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
  await h.click({ id: 'Q2', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy', via: 'chat' })
  await clock.advance(120_000)
  expect(await ui.find({ type: 'Text', text: /undelivered/ })).toBeUndefined()
  await clock.advance(240_000)
  const line = await ui.find({ type: 'Text', text: /1 answer undelivered for 5\+ min \(Q1\): is coord running\?/ })
  expect(line).toBeDefined()
  await ui.unmount()
})

// Review 09.11. (findings G § Academy b): the subject's owner gets the answer too, through the same deliverer.
test('the owner of a question gets a copy of the answer; a failed copy is a row, not a routing line', async ($, on) => {
  const board = boardOf({
    owner_queue: [{ id: 'Q1', session: 'asker', key: 'PROJ-40', ask: 'Ship it?', since: '2026-11-03', recommendation: 'yes', owner: 'Vic' }],
  })
  const { clock, h } = await coordinator($, on, {
    board,
    send: to => (to === 'Vic' ? { isDelivered: false, reason: 'No agent named Vic is reachable' } : { isDelivered: true }),
  })
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(3_000)
  expect(h.sent.map(s => s.to).sort()).toEqual(['Vic', 'asker'])
  expect(h.sent.find(s => s.to === 'Vic')?.text).toBe(
    'Q1: proposal accepted (answered from the board pane in foxy)\n(copy for the owner of this subject)',
  )
  const rows = h.rows('Q1')
  expect(rows.map(r => [r.role, r.delivered]).sort()).toEqual([
    ['asker', true],
    ['coordinator', true],
    ['owner', false],
  ])
  expect(h.submitted).toEqual(['Q1: proposal accepted (answered from the board pane in foxy)'])
})

test('an owner who is the asker or the writer gets no second copy', async ($, on) => {
  const board = boardOf({
    owner_queue: [{ id: 'Q1', session: 'asker', key: 'PROJ-40', ask: 'Ship it?', since: '2026-11-03', recommendation: 'yes', owner: 'asker' }],
  })
  const { clock, h } = await coordinator($, on, { board })
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(3_000)
  expect(h.sent.map(s => s.to)).toEqual(['asker'])
})

test('a reply read from a ticket names the ticket as where it was written', async () => {
  const line = { id: 'Q4', answer: 'accept', ts: '2026-11-03T16:00:00.000Z', session: 'ticket PROJ-12 (bob)' }
  expect(writerNote({ ...line, via: 'ticket' })).toBe(' (answered on ticket PROJ-12 (bob))')
  expect(writerNote({ ...line, via: 'chat' })).toBe(' (answered in the chat of ticket PROJ-12 (bob))')
  expect(writerNote(line)).toBe(' (answered from the board pane in ticket PROJ-12 (bob))')
})

test('a one-way "Yes, I\'ll do it" tells coordinator and asker the owner merges by hand, never "proposal accepted"', async ($, on) => {
  const pr = 'https://github.com/acme/shop/pull/7'
  const board = boardOf({
    owner_queue: [
      { id: 'Q1', session: 'asker', key: 'PROJ-40', ask: 'Merge it?', since: '2026-11-03', recommendation: 'yes', pr_url: pr, one_way: 'money' },
    ],
  })
  const { clock, h } = await coordinator($, on, { board })
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(3_000)
  const text = `Q1: the owner approves or merges ${pr} by hand — do not merge or arm it; the question stays open until the PR is merged (answered from the board pane in foxy)`
  expect(h.submitted).toEqual([text])
  expect(h.sent).toEqual([{ to: 'asker', text }])
  expect([...h.submitted, ...h.sent.map(s => s.text)].some(t => t.includes('proposal accepted'))).toBe(false)
})

test('Taken on a task says the owner does it; an accept_hand wording leaves the task text alone', async ($, on) => {
  const board = boardOf({
    owner_queue: [{ id: 'Q1', session: 'asker', key: 'PROJ-40', ask: 'Rotate the key', since: '2026-11-03', recommendation: 'today', kind: 'task' }],
    answer_prompts: { accept_hand: '{id}: ich merge {pr} selbst' },
  })
  const { clock, h } = await coordinator($, on, { board })
  await h.click({ id: 'Q1', answer: 'accept', ts: iso(T0 + 1_000), session: 'foxy' })
  await clock.advance(3_000)
  expect(h.submitted).toEqual(['Q1: taken — the owner does this task; do not do it yourself (answered from the board pane in foxy)'])
})
