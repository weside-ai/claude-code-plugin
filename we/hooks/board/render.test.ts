import { expect, mock, test } from 'claude-code/testing'

import { paint } from './paint'

// Shaped like a real orchestrator's board: priorities as one string, three news items (one already read)
// and the older notes string, four questions,
// masters with and without workers, one master resting; two sessions carry the restore fields `cwd`
// and `session_id`, which the pane never shows.
const BOARD = JSON.stringify({
  updated: '2026-10-30T20:59:00+00:00',
  updated_by: 'Orchestrator',
  priorities: 'Finish what is open → money → marketing. The kernel runs on its own.',
  news: [
    { id: 'N3', kind: 'gate', title: 'v2.4.1 is tagged, prod still reports v2.4.0', ts: '2026-10-30T20:40:00+00:00',
      body: 'The rollout hung on a GitHub 502 and was restarted; the lead re-tests once it is live.' },
    { id: 'N2', kind: 'todo', title: 'Sign the processor agreement in the billing dashboard before Friday so the EU checkout can open on time', ts: '2026-10-28' },
    { id: 'N1', title: 'Kernel runs on its own until the money stories merged', ts: '2026-10-27' },
  ],
  notes: 'v2.4.1 is tagged, prod still reports v2.4.0: the rollout hung on a GitHub 502 and was restarted.',
  answer_prompts: { accept: '{id}: Vorschlag angenommen' },
  owner_queue: [
    { id: 'Q19', session: 'legal', key: 'PROJ-69', since: '2026-10-30', recommendation: 'keep it closed until demand is measurable',
      ask: 'UK: register with the tax office (quarterly returns, running cost) or keep the web checkout closed for the UK? The UK then buys in the app' },
    { id: 'Q12', session: 'billing', key: 'PROJ-59', ask: 'Merge PR #562? (money path, CI green)', since: '2026-10-28', recommendation: 'yes' },
    { id: 'Q17', session: 'apps', key: 'PROJ-65..68', ask: 'Release 4 app images (artwork/v2/)', since: '2026-10-30', recommendation: 'release' },
    { id: 'Q9', session: 'lead', key: 'PROJ-40', ask: 'Storyline S1–S3', since: '2026-10-21' },
  ],
  sessions: [
    { name: 'lead', role: 'master', companion: 'Lead', keys: ['PROJ-40'], topic: 'Handoffs companion ↔ company', now: 'waits for the v2.4.1 rollout, then a re-test', state: 'wait-owner', priority: 1,
      cwd: '/home/me/work/lead', session_id: '0b5c1e2a-7f3d-4c11-9a8e-1d2f3a4b5c6d' },
    { name: 'apps', role: 'master', keys: ['PROJ-65', 'PROJ-66', 'PROJ-67', 'PROJ-68'], topic: '4 expert apps + image budget', now: '#563 today; apps tomorrow', state: 'build', priority: 2 },
    { name: 'img', role: 'worker', parent: 'apps', keys: ['PROJ-65'], now: 'renders the second artwork batch for the journal and the tracker app', state: 'build', pr: 563,
      cwd: '/home/me/work/apps', session_id: '9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b' },
    { name: 'billing', role: 'master', companion: 'Vera', keys: ['PROJ-60'], topic: 'Account currency EUR/USD', now: '#562 green (Q12); #564 metering, CI runs; two stories in build. Merge migrations serially', state: 'wait-owner', pr: 562, priority: 3, direction: 'money first' },
    { name: 'meter', role: 'worker', parent: 'billing', keys: ['PROJ-63'], now: 'CI', state: 'ci', pr: 564 },
    { name: 'kernel', role: 'master', keys: ['PROJ-17'], topic: 'Kernel (long-term)', now: 'runs on its own', state: 'idle', priority: 4 },
  ],
})

const PROBE = JSON.stringify({
  sessions: [
    { name: 'lead', pid: 1, status: 'waiting', weRole: 'master', profile: '3-me_example.com', envRead: true, mode: 'bypassPermissions' },
    { name: 'apps', pid: 2, status: 'busy', weRole: null, profile: null, envRead: true, mode: 'bypassPermissions' },
    { name: 'img', pid: 3, status: 'busy', weRole: 'worker', profile: null, envRead: true, mode: 'bypassPermissions' },
    { name: 'billing', pid: 4, status: 'busy', weRole: 'master', profile: '3-me_example.com', envRead: true, mode: 'bypassPermissions' },
    { name: 'meter', pid: 5, status: 'busy', weRole: 'worker', profile: null, envRead: true, mode: 'auto' },
    { name: 'stray', pid: 6, status: 'idle', envRead: true, mode: 'bypassPermissions' },
  ],
})

const ANSWERS = [
  { id: 'Q12', answer: 'accept', ts: '2026-10-30T21:02:00.000Z', session: 'Orchestrator' },
  { id: 'N1', answer: 'read', ts: '2026-10-30T21:03:00.000Z', session: 'Orchestrator' },
].map(a => `${JSON.stringify(a)}\n`).join('')

const RUN = (stdout: string) => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })

// Today's pane before the Work toggle: closed, a box differs from it only by the toggle. N1 is read and
// gone; the older notes string folds to one line.
const AT_100 = `
◆ Board  as of 12 min ago (Orchestrator)
████████████░░░░  3/4 masters active · 4 waiting for you · 1 in CI
Finish what is open → money → marketing. The kernel runs on its own.

╭──────────────────────────────────────────────────────────────────────────────────────────────────╮
│ News (2)                                                                                         │
│ [ Read ] ⚑ v2.4.1 is tagged, prod still reports v2.4.0  today                                    │
│            The rollout hung on a GitHub 502 and was restarted; the lead re-tests once it is      │
│            live.                                                                                 │
│ [ Read ] ◉ Sign the processor agreement in the billing dashboard before Friday so the EU c…  2 d │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

[ ▸ Notes ]  v2.4.1 is tagged, prod still reports v2.4.0: the rollout hung on a GitHub 502 and was …

╭──────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Waiting for you (4)                                                                              │
│                                                                                                  │
│ Q9  9 d  lead  PROJ-40                                                                           │
│ Storyline S1–S3                                                                                  │
│ [ Deny ] [ Discuss ] [ More info ]                                                               │
│                                                                                                  │
│ Q12  2 d  billing  PROJ-59                                                                       │
│ Merge PR #562? (money path, CI green)                                                            │
│ → yes                                                                                            │
│ [ Accept ] [ Deny ] [ Discuss ] [ More info ] ✓ accepted 21:02 UTC (Orchestrator)                │
│                                                                                                  │
│ Q19  today  legal  PROJ-69                                                                       │
│ UK: register with the tax office (quarterly returns, running cost) or keep the web checkout      │
│ closed for the UK? The UK then buys in the app                                                   │
│ → keep it closed until demand is measurable                                                      │
│ [ Accept ] [ Deny ] [ Discuss ] [ More info ]                                                    │
│                                                                                                  │
│ Q17  today  apps  PROJ-65..68                                                                    │
│ Release 4 app images (artwork/v2/)                                                               │
│ → release                                                                                        │
│ [ Accept ] [ Deny ] [ Discuss ] [ More info ]                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

╭──────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ◉ lead  [Lead]  PROJ-40  waiting  ● bypass  P1                                                   │
│ Handoffs companion ↔ company                                                                     │
│ waits for the v2.4.1 rollout, then a re-test                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭──────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ◉ billing  [Vera]  PROJ-60  #562  busy  ● bypass                                                 │
│ Account currency EUR/USD                                                                         │
│ #562 green (Q12); #564 metering, CI runs; two stories in build. Merge migrations serially        │
│ P3 · money first                                                                                 │
│                                                                                                  │
│ └ ● meter  PROJ-63  #564  busy  ●  CI                                                            │
│     mode auto differs (most run bypass)                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭──────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ● apps  PROJ-65 PROJ-66 PROJ-67 PROJ-68  busy  ● bypass  P2                                      │
│ WE_ROLE missing — restart it as a master                                                         │
│ 4 expert apps + image budget                                                                     │
│ #563 today; apps tomorrow                                                                        │
│                                                                                                  │
│ └ ● img  PROJ-65  #563  busy  ●  renders the second artwork batch for the journal and the track… │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

[ + 2 idle/other ]

[ Refresh ]  [ Flow ]  file 21:11 UTC · live 21:11 UTC · watch 3 s, all 1 min
● runs  ◉ waits for you  ○ rests  ? unknown  second ● = start mode`

const AT_60 = `
◆ Board  as of 12 min ago (Orchestrator)
████████████░░░░  3/4 masters active · 4 waiting for you
1 in CI
Finish what is open → money → marketing. The kernel runs on
its own.

╭──────────────────────────────────────────────────────────╮
│ News (2)                                                 │
│ [ Read ] ⚑ v2.4.1 is tagged, prod still reports …  today │
│            The rollout hung on a GitHub 502 and was      │
│            restarted; the lead re-tests once it is live. │
│ [ Read ] ◉ Sign the processor agreement in the bil…  2 d │
╰──────────────────────────────────────────────────────────╯

[ ▸ Notes ]  v2.4.1 is tagged, prod still reports v2.4.0: t…

╭──────────────────────────────────────────────────────────╮
│ Waiting for you (4)                                      │
│                                                          │
│ Q9  9 d  lead  PROJ-40                                   │
│ Storyline S1–S3                                          │
│ [ Deny ] [ Discuss ] [ More info ]                       │
│                                                          │
│ Q12  2 d  billing  PROJ-59                               │
│ Merge PR #562? (money path, CI green)                    │
│ → yes                                                    │
│ [ Accept ] [ Deny ] [ Discuss ] [ More info ]            │
│ ✓ accepted 21:02 UTC (Orchestrator)                      │
│                                                          │
│ Q19  today  legal  PROJ-69                               │
│ UK: register with the tax office (quarterly returns,     │
│ running cost) or keep the web checkout closed for the    │
│ UK? The UK then buys in the app                          │
│ → keep it closed until demand is measurable              │
│ [ Accept ] [ Deny ] [ Discuss ] [ More info ]            │
│                                                          │
│ Q17  today  apps  PROJ-65..68                            │
│ Release 4 app images (artwork/v2/)                       │
│ → release                                                │
│ [ Accept ] [ Deny ] [ Discuss ] [ More info ]            │
╰──────────────────────────────────────────────────────────╯

╭──────────────────────────────────────────────────────────╮
│ ◉ lead  [Lead]  PROJ-40  waiting  ● bypass  P1           │
│ Handoffs companion ↔ company                             │
│ waits for the v2.4.1 rollout, then a re-test             │
╰──────────────────────────────────────────────────────────╯
╭──────────────────────────────────────────────────────────╮
│ ◉ billing  [Vera]  PROJ-60  #562  busy  ● bypass         │
│ Account currency EUR/USD                                 │
│ #562 green (Q12); #564 metering, CI runs; two stories in │
│ build. Merge migrations serially                         │
│ P3 · money first                                         │
│                                                          │
│ └ ● meter  PROJ-63  #564  busy  ●  CI                    │
│     mode auto differs (most run bypass)                  │
╰──────────────────────────────────────────────────────────╯
╭──────────────────────────────────────────────────────────╮
│ ● apps  PROJ-65 PROJ-66 PROJ-67 PROJ-68  busy  ● bypass  │
│ P2                                                       │
│ WE_ROLE missing — restart it as a master                 │
│ 4 expert apps + image budget                             │
│ #563 today; apps tomorrow                                │
│                                                          │
│ └ ● img  PROJ-65  #563  busy  ●  renders the second art… │
╰──────────────────────────────────────────────────────────╯

[ + 2 idle/other ]

[ Refresh ]  [ Flow ]
file 21:11 UTC · live 21:11 UTC · watch 3 s, all 1 min
● runs  ◉ waits for you  ○ rests  ? unknown
second ● = start mode`

// The Work toggle out of a closed box: from the title line, or the line it stands on alone.
const withoutToggle = (lines: string[]) =>
  lines.filter(line => !/^│ \[ ▸ Work \] +│$/.test(line)).map(line => line.replace('  [ ▸ Work ]', ' '.repeat(12)))

test('/board at 100 and 60 columns: frames, cards and folded rest, no line past the pane', { options: { masterProfile: 'me_example.com' } }, async ($, on) => {
  const clock = mock.clock(on, { now: Date.parse('2026-10-30T21:11:00Z') })
  mock.store(on)
  on('env.get', () => ({ value: '/home/me' }))
  on('fs.exists', () => ({ value: true }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 1, isLink: false } }))
  on('fs.read', (_$, e) => ({ value: String((e as { path?: unknown }).path).endsWith('.jsonl') ? ANSWERS : BOARD }))
  on('process.run', () => RUN(PROBE))
  on('ui.open', () => ({ value: { isPlaced: true } }))

  await $.command.run({ command: 'board', args: '', origin: { kind: 'composer' } } as never)
  await clock.settle()

  const draw = async (columns: number) => {
    const ui = await $.ui.mount({ plugin: 'we', surface: 'terminal', component: 'Pane', requestId: 'we-board', props: { bodyColumns: columns } as never })
    const text = async () => paint((await ui.drawn()) as never, columns)
    const folded = await text()
    await ui.press({ key: 'rest' })
    const open = await text()
    await ui.press({ key: 'rest' })
    await ui.unmount()
    return { folded, open }
  }

  const wide = await draw(100)
  expect(`\n${withoutToggle(wide.folded).join('\n')}`).toBe(AT_100)
  const narrow = await draw(60)
  expect(`\n${withoutToggle(narrow.folded).join('\n')}`).toBe(AT_60)
  // Every master with keys carries the closed toggle; at 60 columns it moves to a line of its own.
  expect(wide.folded.filter(line => line.includes('[ ▸ Work ]')).length).toBe(3)
  expect(narrow.folded).toContain('│ [ ▸ Work ]'.padEnd(59) + '│')
  for (const { folded, open } of [wide, narrow]) {
    expect(Math.max(...[...folded, ...open].map(line => line.length))).toBeLessThanOrEqual(folded === wide.folded ? 100 : 60)
  }
  // The narrow pane breaks between segments, never inside a frame's border.
  expect(narrow.folded.filter(line => line.startsWith('│')).every(line => line.length === 60 && line.endsWith('│'))).toBe(true)
  expect(narrow.folded).toContain('████████████░░░░  3/4 masters active · 4 waiting for you')
  expect(narrow.folded).toContain('│ └ ● img  PROJ-65  #563  busy  ●  renders the second art… │')
  // Opened, the rest shows the resting master in its frame and the sessions on no board.
  expect(narrow.open).toContain('[ − 2 idle/other ]')
  expect(narrow.open.some(line => line.startsWith('│ ○ kernel  PROJ-17  gone'))).toBe(true)
  expect(narrow.open).toContain('Live, not on the board: stray')
  // The restore fields stay off the pane at every width.
  for (const line of [...wide.folded, ...wide.open, ...narrow.folded, ...narrow.open]) {
    expect(/\/home\/me\/work|0b5c1e2a|9e8d7c6b/.test(line)).toBe(false)
  }
})
