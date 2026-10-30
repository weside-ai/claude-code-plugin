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
  expect(reads).toEqual(['/home/me/.claude/we-state/board.json'])

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
  expect(reads).toEqual(['/home/me/boards/team.json'])
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
  on('fs.read', () => {
    reads += 1
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
