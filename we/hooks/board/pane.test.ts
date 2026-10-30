import { expect, mock, test } from 'claude-code/testing'

const BOARD = JSON.stringify({
  updated: '2026-10-30T18:10:00+01:00',
  updated_by: 'Orchestrator',
  owner_queue: [
    { id: 'Q1', session: 'lead', key: 'PROJ-40', ask: 'Live test AC 16', since: '2026-10-30', recommendation: 'tonight' },
    { id: 'Q2', session: 'marketing', key: 'PROJ-41', ask: 'Storyline S1–S3', since: '2026-10-21', recommendation: '' },
  ],
  sessions: [
    { name: 'CTA', role: 'master', companion: null, parent: null, keys: ['PROJ-55'], topic: 'Bugs', now: 'three workers', state: 'build', pr: null, priority: null, direction: null },
    { name: 'chip', role: 'worker', parent: 'CTA', keys: ['PROJ-57'], topic: 'Chip', now: 'CI', state: 'ci', pr: 5560 },
    { name: 'onboarding', role: 'master', parent: null, keys: [], topic: 'Onboarding', state: 'build', note: 'WE_ROLE missing' },
    { name: 'lead', role: 'master', companion: 'Lead', parent: null, keys: ['PROJ-40'], topic: 'Handoff', state: 'wait-owner', priority: 2, direction: 'test live' },
  ],
})

const PROBE = JSON.stringify({
  sessions: [
    { name: 'CTA', pid: 1, status: 'idle', weRole: 'master', profile: '3-me_example.com', envRead: true, mode: 'bypassPermissions' },
    { name: 'chip', pid: 2, status: 'busy', weRole: 'worker', profile: null, envRead: true, mode: 'bypassPermissions' },
    { name: 'onboarding', pid: 3, status: 'waiting', weRole: null, profile: null, envRead: true, mode: 'bypassPermissions' },
    { name: 'stray', pid: 4, status: 'idle', envRead: true, mode: 'auto' },
  ],
})

const RUN = (stdout: string) => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })

test('/board draws the queue oldest first, masters with workers, live and start-mode lamps', { options: { masterProfile: 'me_example.com' } }, async ($, on) => {
  const clock = mock.clock(on)
  mock.store(on)
  on('env.get', () => ({ value: '/home/me' }))
  on('fs.exists', () => ({ value: true }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 1, isLink: false } }))
  const reads: string[] = []
  on('fs.read', (_$, e) => {
    reads.push(String((e as { path?: unknown }).path))
    return { value: BOARD }
  })
  // The Flow button opens the flow pane for the branch's key; its git and gh reads answer empty.
  on('process.run', (_$, e) => RUN(e.argv[0] === 'python3' ? PROBE : e.argv.join(' ') === 'git branch --show-current' ? 'feat/PROJ-9-x' : ''))
  on('session.id', () => ({ value: 's1' }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.log', () => ({ value: undefined }))
  const opened: string[] = []
  on('ui.open', (_$, e) => {
    opened.push(String((e as { id?: unknown }).id))
    return { value: { isPlaced: true } }
  })

  const answer = await $.command.run({ command: 'board', args: '', origin: { kind: 'composer' } } as never)
  expect(answer.text).toBe('Board pane opened.')
  await clock.settle()
  expect(reads).toEqual(['/home/me/.claude/we-state/board.json', '/home/me/.claude/we-state/board-answers.jsonl'])

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'we', surface, component: 'Pane', requestId: 'we-board', props: { bodyColumns: 80 } as never })
    expect(await ui.find({ type: 'Text', text: /Waiting for the owner \(2\)/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /as of .* ago \(Orchestrator\)/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /→ tonight/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /WE_ROLE missing · not in the master profile — restart it as a master/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /P2 · test live/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Live, not on the board: stray/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /#5560/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /⚠ WE_ROLE missing/ })).toBeDefined()
    await ui.press({ key: 'flow' })
    await ui.unmount()
  }
  await clock.settle()
  expect(opened).toEqual(['we-board', 'we-flow', 'we-flow'])
})

test('without masterProfile no master is red; boardFile moves the file', { options: { boardFile: '~/boards/team.json' } }, async ($, on) => {
  const clock = mock.clock(on)
  mock.store(on)
  on('env.get', () => ({ value: '/home/me' }))
  on('fs.exists', () => ({ value: true }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 1, isLink: false } }))
  const reads: string[] = []
  on('fs.read', (_$, e) => {
    reads.push(String((e as { path?: unknown }).path))
    return { value: BOARD }
  })
  on('process.run', () => RUN(PROBE))
  on('ui.open', () => ({ value: { isPlaced: true } }))

  await $.command.run({ command: 'board', args: '', origin: { kind: 'composer' } } as never)
  await clock.settle()
  expect(reads).toEqual(['/home/me/boards/team.json', '/home/me/boards/board-answers.jsonl'])
  const ui = await $.ui.mount({ plugin: 'we', surface: 'terminal', component: 'Pane', requestId: 'we-board', props: { bodyColumns: 80 } as never })
  expect(await ui.find({ type: 'Text', text: /restart it as a master/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /Waiting for the owner \(2\)/ })).toBeDefined()
  await ui.unmount()
})

test('a missing board file says who writes it and where the schema is', async ($, on) => {
  const clock = mock.clock(on)
  mock.store(on)
  on('env.get', () => ({ value: '/home/me' }))
  on('fs.exists', () => ({ value: false }))
  on('process.run', () => RUN('{"sessions":[]}'))
  on('ui.open', () => ({ value: { isPlaced: true } }))

  await $.command.run({ command: 'board', args: '', origin: { kind: 'composer' } } as never)
  await clock.settle()
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'we', surface, component: 'Pane', requestId: 'we-board', props: { bodyColumns: 80 } as never })
    expect(await ui.find({ type: 'Text', text: /No board yet: your orchestrator session writes \/home\/me\/\.claude\/we-state\/board\.json; the schema is in .*docs\/board\.md\./ })).toBeDefined()
    await ui.unmount()
  }
})

test('the pane polls nothing before /board, then re-reads only when the mtime moved', async ($, on) => {
  const clock = mock.clock(on)
  mock.store(on)
  on('env.get', () => ({ value: '/home/me' }))
  on('fs.exists', () => ({ value: true }))
  let mtimeMs = 1
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs, isLink: false } }))
  let reads = 0
  on('fs.read', (_$, e) => {
    if (String((e as { path?: unknown }).path).endsWith('board.json')) reads += 1
    return { value: BOARD }
  })
  let probes = 0
  on('process.run', (_$, e) => {
    if (e.argv[0] === 'python3') probes += 1
    return RUN(PROBE)
  })
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('command.register', () => ({ value: { command: 'board' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(10_000)
  expect(reads).toBe(0)

  await $.command.run({ command: 'board', args: '', origin: { kind: 'composer' } } as never)
  await clock.settle()
  expect([reads, probes]).toEqual([1, 1])

  await clock.advance(9_000)
  expect(reads).toBe(1)
  mtimeMs = 2
  await clock.advance(3_000)
  expect(reads).toBe(2)
})

// A fake home: board.json, and board-answers.jsonl once answer.py appended to it.
function answersHome(on: Parameters<Parameters<typeof test>[1]>[1], self: { sessionId: string; name: string }) {
  const answersPath = '/home/me/.claude/we-state/board-answers.jsonl'
  let lines = ''
  let mtimeMs = 1
  const appended: string[][] = []
  const submitted: string[] = []
  on('env.get', () => ({ value: '/home/me' }))
  on('fs.exists', (_$, e) => ({ value: String((e as { path?: unknown }).path) !== answersPath || lines !== '' }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs, isLink: false } }))
  on('fs.read', (_$, e) => ({ value: String((e as { path?: unknown }).path) === answersPath ? lines : BOARD }))
  on('session.id', () => ({ value: self.sessionId }))
  on('process.run', (_$, e) => {
    if (String(e.argv[2]).endsWith('/answer.py')) {
      appended.push(e.argv.slice(3))
      const [, id, answer, ts, session] = e.argv.slice(3)
      lines += `${JSON.stringify({ id, answer, ts, session: session ?? null })}\n`
      mtimeMs += 1
      return RUN('')
    }
    return RUN(JSON.stringify({ sessions: [{ name: self.name, sessionId: self.sessionId, pid: 9, status: 'busy', envRead: false }] }))
  })
  on('prompt.submit', (_$, e) => {
    submitted.push(String((e as { text?: unknown }).text))
    return { text: String((e as { text?: unknown }).text) }
  })
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', (_$, e) => {
    throw new Error(`unexpected toast: ${String((e as { text?: unknown }).text)}`)
  })
  return { answersPath, appended, submitted }
}

test('Accept in the orchestrator session appends one line, sends the prompt and shows the answer', async ($, on) => {
  const clock = mock.clock(on)
  mock.store(on)
  const home = answersHome(on, { sessionId: 's-orch', name: 'Orchestrator' })

  await $.command.run({ command: 'board', args: '', origin: { kind: 'composer' } } as never)
  await clock.settle()
  const ui = await $.ui.mount({ plugin: 'we', surface: 'terminal', component: 'Pane', requestId: 'we-board', props: { bodyColumns: 80 } as never })
  // Q2 has no recommendation: no Accept, but Discuss and More info.
  expect(await ui.find({ key: 'accept-Q2' })).toBeUndefined()
  expect(await ui.find({ key: 'discuss-Q2' })).toBeDefined()
  await ui.press({ key: 'accept-Q1' })
  await clock.settle()
  expect(home.appended).toHaveLength(1)
  expect(home.appended[0]).toEqual([home.answersPath, 'Q1', 'accept', expect.stringMatching(/^\d{4}-\d\d-\d\dT/), 'Orchestrator'])
  expect(home.submitted).toEqual(['Q1: proposal accepted'])
  expect(await ui.find({ type: 'Text', text: /✓ accepted \d\d:\d\d UTC \(Orchestrator\)/ })).toBeDefined()

  await ui.press({ key: 'info-Q2' })
  await clock.settle()
  expect(home.submitted).toEqual(['Q1: proposal accepted', 'Q2: I need more information'])
  expect(await ui.find({ type: 'Text', text: /✓ more info asked/ })).toBeDefined()
  await ui.unmount()
})

test('a press in any other session only appends the line, named after that session', async ($, on) => {
  const clock = mock.clock(on)
  mock.store(on)
  const home = answersHome(on, { sessionId: 's-lead', name: 'lead' })

  await $.command.run({ command: 'board', args: '', origin: { kind: 'composer' } } as never)
  await clock.settle()
  const ui = await $.ui.mount({ plugin: 'we', surface: 'terminal', component: 'Pane', requestId: 'we-board', props: { bodyColumns: 80 } as never })
  await ui.press({ key: 'discuss-Q1' })
  await clock.settle()
  expect(home.appended.map(a => [a[1], a[2], a[4]])).toEqual([['Q1', 'discuss', 'lead']])
  expect(home.submitted).toEqual([])
  expect(await ui.find({ type: 'Text', text: /✓ discuss \d\d:\d\d UTC \(lead\)/ })).toBeDefined()
  await ui.unmount()
})
