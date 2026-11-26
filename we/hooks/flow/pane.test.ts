import { expect, mock, test } from 'claude-code/testing'

const STORY = 'docs/plans/PROJ-12-story.md'
const answers: [RegExp, string][] = [
  [/^git rev-parse --show-toplevel/, '/repo\n'],
  [/^git grep -l -E \^ticket: PROJ-10\$/, 'origin/main:docs/plans/channels-epic.md\n'],
  [/^git grep -h -m1/, '# Epic: Channels\n'],
  [/^git grep -l -E \^epic: \(PROJ-10\|channels\)\$/, `origin/main:${STORY}\norigin/main:docs/plans/PROJ-14-story.md\n`],
  [/^git grep -E -e/, [
    `origin/main:${STORY}:story: PROJ-12`, `origin/main:${STORY}:epic: PROJ-10`, `origin/main:${STORY}:status: approved`,
    `origin/main:${STORY}:# Plan: Discord groups`,
    'origin/main:docs/plans/PROJ-14-story.md:story: PROJ-14', 'origin/main:docs/plans/PROJ-14-story.md:epic: PROJ-10',
    'origin/main:docs/plans/PROJ-14-story.md:status: approved', 'origin/main:docs/plans/PROJ-14-story.md:# Plan: Guild identity',
  ].join('\n')],
  [/^git for-each-ref/, 'main\norigin/feat/PROJ-14-guild\n'],
  [/^git worktree list/, 'worktree /repo\nbranch refs/heads/main\n'],
  [/^git rev-list --count/, '3\n'],
  [/^gh pr list/, JSON.stringify([
    { number: 5072, state: 'MERGED', headRefName: 'feat/PROJ-12-discord', title: 'x', autoMergeRequest: null, statusCheckRollup: [] },
    { number: 5090, state: 'OPEN', headRefName: 'feat/PROJ-14-guild', title: 'y', autoMergeRequest: null,
      statusCheckRollup: [{ name: 'CI Summary', status: 'COMPLETED', conclusion: 'FAILURE' }, { name: 'Claude Review', status: 'IN_PROGRESS', conclusion: null }] },
  ])],
]

test('/flow PROJ-10 fills the pane after the command returned', async ($, on) => {
  const clock = mock.clock(on)
  mock.store(on)
  on('process.run', (_$, e) => {
    const line = e.argv.join(' ')
    const hit = answers.find(([pattern]) => pattern.test(line))
    return { value: { exitCode: 0, stdout: hit?.[1] ?? '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  // The Board button opens the board pane, which looks for its file.
  on('env.get', () => ({ value: '/home/me' }))
  on('fs.exists', () => ({ value: false }))
  const toasts: string[] = []
  on('ui.toast', (_$, e) => {
    toasts.push(String((e as { text?: unknown }).text))
    return { value: undefined }
  })
  const opened: string[] = []
  on('ui.open', (_$, e) => {
    opened.push(String((e as { id?: unknown }).id))
    return { value: { isPlaced: true } }
  })
  on('ui.status', () => ({ value: undefined }))
  const logged: string[] = []
  on('ui.log', (_$, e) => {
    logged.push(String((e as { text?: unknown }).text))
    return { value: undefined }
  })
  const ran: string[] = []
  on('command.run', { command: 'we:ci-review' }, (_$, e) => {
    ran.push(`${e.command} ${e.args}`)
    return { text: 'ok' }
  })
  on('command.run', { command: 'we:standup' }, (_$, e) => {
    ran.push(`${e.command} ${e.args}`)
    return { text: 'ok' }
  })

  const answer = await $.command.run({ command: 'flow', args: 'PROJ-10', origin: { kind: 'composer' } } as never)
  expect(answer.text).toContain('PROJ-10')
  await clock.settle()
  expect(logged).toEqual([])

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'we', surface, component: 'Pane', requestId: 'we-flow', props: { bodyColumns: 70 } as never })
    expect(await ui.find({ type: 'Text', text: /CI red/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /PROJ-12/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /1\/2 merged/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /✗ CI Summary/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Claude running/ })).toBeDefined()
    await ui.press({ key: 'PROJ-14-ci' })
    await ui.press({ key: 'PROJ-14-standup' })
    await ui.press({ key: 'PROJ-10-standup' })
    await ui.press({ key: 'board' })
    await ui.unmount()
  }
  expect(ran).toEqual(['we:ci-review 5090', 'we:standup PROJ-14', 'we:standup PROJ-10', 'we:ci-review 5090', 'we:standup PROJ-14', 'we:standup PROJ-10'])
  await clock.settle()
  expect(toasts).toEqual([])
  expect(opened).toEqual(['we-flow', 'we-board', 'we-board'])
  // The Board button keeps the keys this pane shows: it opens the Board alone.
  const after = await $.ui.mount({ plugin: 'we', surface: 'terminal', component: 'Pane', requestId: 'we-flow', props: { bodyColumns: 70 } as never })
  expect(await after.find({ type: 'Text', text: /PROJ-10/ })).toBeDefined()
  await after.unmount()
})

// flow_intervals.py --snapshot's document, as far as Crew flow reads it.
const SNAP = (generatedAt: string) =>
  JSON.stringify({
    schema_version: 1,
    generated_at: generatedAt,
    project: 'acme/app',
    header: ['one probe every 300 s', 'Not counted: …', 'CI wait: gh check runs, fetched_at 2026-11-20T21:58:00Z'],
    now: [
      { who: 'ABC-1-build', group: 'workers', starter: 'lead', kind: 'waiting:ci', since: '2026-11-20T21:40:00Z', waiting_on: 'ci', key: 'ABC-1', label: null },
      { who: 'lead', group: 'masters', starter: null, kind: 'working', since: '2026-11-20T21:50:00Z', waiting_on: null, key: 'ABC-1', label: null },
      { who: 'ABC-9', group: 'stories', starter: null, kind: 'stage:in_review', since: '2026-11-20T18:00:00Z', waiting_on: null, key: 'ABC-9', label: 'waits on acceptance' },
    ],
    ci: { prs: [{ number: 7, title: 'ABC-1 export', heads: [{ pr: 7, start: '2026-11-20T21:00:00Z', end: '2026-11-20T22:00:00Z', queue_s: 2400, run_s: 900, open: true }] }] },
    gaps: [{ reason: 'no data: sampler 2026-11-19' }],
    page: '/home/me/.claude/we-state/flow/flow-acme-app.html',
  })

test('Flow from the board: Crew flow from the last snapshot, a stale one refreshed once in the background', async ($, on) => {
  const clock = mock.clock(on, { now: Date.parse('2026-11-20T22:00:00Z') })
  mock.store(on)
  const path = '/home/me/.claude/we-state/flow/flow-acme-app.json'
  let snapshot = SNAP('2026-11-20T21:57:00Z') // 3 min old: fresh
  const ran: string[] = []
  on('process.run', (_$, e) => {
    const line = e.argv.join(' ')
    ran.push(line)
    if (line.endsWith('--snapshot-path')) return RUN_OK(`${path}\n`)
    if (line.includes('--snapshot')) {
      snapshot = SNAP('2026-11-20T22:20:00Z')
      return RUN_OK(path)
    }
    return RUN_OK('')
  })
  on('fs.exists', () => ({ value: true }))
  on('fs.read', () => ({ value: snapshot }))
  on('env.get', () => ({ value: '/home/me' }))
  on('session.id', () => ({ value: 's1' }))
  on('session.messages', () => ({ value: [] }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.log', () => ({ value: undefined }))

  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('command.register', () => ({ value: { command: 'flow' } }))
  on('ui.status', () => ({ value: undefined }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  // No key in this session: the pane still opens, Crew flow on top.
  const answer = await $.command.run({ command: 'flow', args: '', origin: { kind: 'composer' } } as never)
  expect(answer.text).toContain('Crew flow')
  await clock.settle()
  const draw = async () => {
    const ui = await $.ui.mount({ plugin: 'we', surface: 'terminal', component: 'Pane', requestId: 'we-flow', props: { bodyColumns: 100 } as never })
    const texts: string[] = []
    for (const re of [/Crew flow/, /ABC-1-build/, /lead  works/, /ABC-9  waits on acceptance/, /#7  queue 40 min · run 15 min/, /gap: no data/, /Swimlanes: \/home\/me/]) {
      const hit = await ui.find({ type: 'Text', text: re })
      texts.push(hit ? String(re) : `missing ${re}`)
    }
    const head = await ui.find({ type: 'Text', text: /Crew flow · acme\/app · snapshot \d+ min old/ })
    await ui.unmount()
    return { texts, head }
  }
  const fresh = await draw()
  expect(fresh.texts.filter(t => t.startsWith('missing'))).toEqual([])
  expect(fresh.head).toBeDefined()
  expect(ran.filter(l => l.includes('--snapshot ') || l.endsWith('--snapshot'))).toEqual([])

  // 20 min later the snapshot is stale: the pane's 2-minute timer starts one background run (no
  // second while the first counts), then the section redraws from it.
  await clock.advance(20 * 60_000)
  await clock.settle()
  const runs = ran.filter(l => / --since 1d --snapshot$/.test(l))
  expect(runs.length).toBe(1)
  const ui = await $.ui.mount({ plugin: 'we', surface: 'terminal', component: 'Pane', requestId: 'we-flow', props: { bodyColumns: 100 } as never })
  expect(await ui.find({ type: 'Text', text: /snapshot 0 min old/ })).toBeDefined()
  await ui.unmount()
})

const RUN_OK = (stdout: string) => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })

// --- /flow without a key in a master: what it orchestrates (standup.py --orchestration) ---------

const ORCH = (masters: unknown[], crewRepo: string | null = '/crew') =>
  JSON.stringify({ schema_version: 1, view: 'orchestration', scope: { key: null, from: 'session', session: 's1', crew_repo: crewRepo }, sources: {}, gaps: [], orchestration: { masters, '(no starter)': [] } })

const LEAD = {
  master: 'lead',
  epic: 'PROJ-10',
  stories: [
    { key: 'PROJ-12', stage: 'done', workers: [] },
    { key: 'PROJ-14', stage: 'in_progress', workers: [{ name: 'PROJ-14-build', state: 'busy' }] },
  ],
  other_workers: [{ name: 'PROJ-99-fix', state: 'idle', key: 'PROJ-99' }],
}

type Script = { exitCode?: number; stdout?: string; reject?: boolean }

async function noKey($: Parameters<Parameters<typeof test>[1]>[0], on: Parameters<Parameters<typeof test>[1]>[1], role: string, script: Script) {
  const clock = mock.clock(on)
  mock.store(on)
  const argv: string[] = []
  on('process.run', (_$, e) => {
    const line = e.argv.join(' ')
    argv.push(line)
    if (line.includes('standup.py')) {
      if (script.reject) return { deny: 'timed out after 30000 ms' }
      return { value: { exitCode: script.exitCode ?? 0, stdout: script.stdout ?? '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    if (line === 'git branch --show-current') return RUN_OK('feat/PROJ-14-guild\n')
    const hit = answers.find(([pattern]) => pattern.test(line))
    return RUN_OK(hit?.[1] ?? '')
  })
  on('env.get', (_$, e) => ({ value: (e as { name?: unknown }).name === 'WE_ROLE' ? role : '/home/me' }))
  const reads: string[] = []
  on('fs.read', (_$, e) => {
    reads.push(String((e as { path?: unknown }).path))
    return { deny: 'ENOENT' }
  })
  on('fs.exists', () => ({ value: false }))
  on('session.id', () => ({ value: 's1' }))
  on('session.messages', () => ({ value: [] }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.status', () => ({ value: undefined }))
  // only /flow's own lines: the session start also starts the board pane, which logs its own
  const logged: string[] = []
  on('ui.log', (_$, e) => {
    const text = String((e as { text?: unknown }).text)
    if (text.startsWith('flow:')) logged.push(text)
    return { value: undefined }
  })
  on('ui.toast', () => ({ value: undefined }))
  const ran: string[] = []
  for (const command of ['we:standup', 'we:epic', 'we:master', 'we:ci-review']) {
    on('command.run', { command }, (_$, e) => {
      ran.push(`${e.command} ${e.args}`)
      return { text: 'ok' }
    })
  }
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('command.register', () => ({ value: { command: 'flow' } }))
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  const answer = await $.command.run({ command: 'flow', args: '', origin: { kind: 'composer' } } as never)
  await clock.settle()
  const mount = () => $.ui.mount({ plugin: 'we', surface: 'terminal', component: 'Pane', requestId: 'we-flow', props: { bodyColumns: 90 } as never })
  return { answer, argv, reads, logged, ran, clock, mount }
}

test('master view: the epic, its stories with their workers, other workers, and the epic Standup', async ($, on) => {
  const r = await noKey($, on, 'master', { stdout: ORCH([LEAD]) })
  expect(r.answer.text).toContain('from master lead')
  expect(r.logged).toEqual([])
  const ui = await r.mount()
  for (const re of [/^Epic PROJ-10/, /PROJ-14/, /^✓ /, /⚙ PROJ-14-build · busy/, /detected from master lead/, /other workers: PROJ-99-fix \(PROJ-99\) · idle/]) {
    expect({ re: String(re), hit: !!(await ui.find({ type: 'Text', text: re })) }).toEqual({ re: String(re), hit: true })
  }
  expect(await ui.find({ type: 'Text', text: /no crew repo/ })).toBeUndefined()
  await ui.press({ key: 'PROJ-10-standup' })
  await ui.press({ key: 'PROJ-14-standup' })
  await ui.unmount()
  expect(r.ran).toEqual(['we:standup PROJ-10', 'we:standup PROJ-14'])
  expect(r.reads.filter(p => p.includes('we-focus'))).toEqual([])
  expect(r.argv).not.toContain('git branch --show-current')
  expect(r.argv.filter(l => l.includes('standup.py'))).toEqual([expect.stringMatching(/standup\.py --orchestration --session s1 --json$/)])
})

test('master view: a master without epic shows its stories as story groups', async ($, on) => {
  const free = { master: 'kiska', epic: null, stories: [{ key: 'PROJ-31', workers: [{ name: 'PROJ-31-build', state: 'idle' }] }, { key: 'PROJ-32', workers: [] }], other_workers: [] }
  const r = await noKey($, on, 'master', { stdout: ORCH([free]) })
  const ui = await r.mount()
  expect(await ui.find({ type: 'Text', text: /◆ PROJ-31 · PROJ-32/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /⚙ PROJ-31-build · idle/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Epic / })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /other workers/ })).toBeUndefined()
  await ui.unmount()
})

test('master view: no crew repo found is one visible line, stories from the board line', async ($, on) => {
  const r = await noKey($, on, 'master', { stdout: ORCH([LEAD], null) })
  const ui = await r.mount()
  expect(await ui.find({ type: 'Text', text: /master lead: no crew repo found — stories from the board line/ })).toBeDefined()
  await ui.unmount()
})

test('a non-master runs no standup.py and detects its branch as before', async ($, on) => {
  const r = await noKey($, on, 'worker', { stdout: ORCH([LEAD]) })
  expect(r.answer.text).toContain('PROJ-14 (from branch feat/PROJ-14-guild)')
  expect(r.argv.filter(l => l.includes('standup.py'))).toEqual([])
  expect(r.logged).toEqual([])
})

for (const [arm, script, reason] of [
  ['exit 1', { exitCode: 1 }, 'standup.py exit 1'],
  ['no JSON', { stdout: 'Traceback …' }, 'standup.py printed no JSON'],
  ['orchestration null', { stdout: JSON.stringify({ orchestration: null }) }, 'orchestration: null'],
  ['no entry', { stdout: ORCH([]) }, 'no entry for this session'],
  ['timeout', { reject: true }, 'timed out'],
] as [string, Script, string][]) {
  test(`master lookup fails (${arm}): the branch as before and one ui.log line`, async ($, on) => {
    const r = await noKey($, on, 'master', script)
    expect(r.answer.text).toContain('PROJ-14 (from branch feat/PROJ-14-guild)')
    expect(r.logged).toHaveLength(1)
    expect(r.logged[0]).toMatch(new RegExp(`^flow: master view unavailable: .*${reason.replace(/[()]/g, '\\$&')}`))
  })
}

test('the 2-minute refresh re-reads the master and keeps the last record when that fails', async ($, on) => {
  let calls = 0
  const busy = ORCH([LEAD])
  const idle = ORCH([{ ...LEAD, stories: [LEAD.stories[0], { ...LEAD.stories[1], workers: [{ name: 'PROJ-14-build', state: 'idle' }] }] }])
  const script: Script = {}
  Object.defineProperty(script, 'stdout', { get: () => [busy, idle][calls++] ?? '' })
  Object.defineProperty(script, 'exitCode', { get: () => (calls > 2 ? 1 : 0) })
  const r = await noKey($, on, 'master', script)
  expect(calls).toBe(1) // the open reuses the lookup of detect()
  await r.clock.advance(120_000)
  await r.clock.settle()
  let ui = await r.mount()
  expect(await ui.find({ type: 'Text', text: /⚙ PROJ-14-build · idle/ })).toBeDefined()
  await ui.unmount()
  await r.clock.advance(120_000)
  await r.clock.settle()
  ui = await r.mount()
  expect(await ui.find({ type: 'Text', text: /⚙ PROJ-14-build · idle/ })).toBeDefined()
  await ui.unmount()
  expect(r.logged.filter(l => l.startsWith('flow: master view unavailable'))).toHaveLength(1)
})

test('a master without epic sees a story it gains after the open, with its worker, on the refresh', async ($, on) => {
  let calls = 0
  const one = { master: 'kiska', epic: null, stories: [{ key: 'PROJ-31', workers: [] }], other_workers: [] }
  const two = { ...one, stories: [...one.stories, { key: 'PROJ-33', workers: [{ name: 'PROJ-33-build', state: 'busy' }] }] }
  const script: Script = {}
  Object.defineProperty(script, 'stdout', { get: () => [ORCH([one]), ORCH([two])][Math.min(calls++, 1)] })
  const r = await noKey($, on, 'master', script)
  let ui = await r.mount()
  expect(await ui.find({ type: 'Text', text: /PROJ-33/ })).toBeUndefined()
  await ui.unmount()
  await r.clock.advance(120_000)
  await r.clock.settle()
  ui = await r.mount()
  expect(await ui.find({ type: 'Text', text: /◆ PROJ-31 · PROJ-33/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /⚙ PROJ-33-build · busy/ })).toBeDefined()
  await ui.unmount()
})
