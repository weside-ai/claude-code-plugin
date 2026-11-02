import { expect, test } from 'claude-code/testing'

import {
  ageDays, answerPrompt, answersPathOf, clip, countBoard, freshness, groupSessions, isMasterProfile, isResting, lastAnswers, liveByName,
  majorityMode, ownName, pack, parseBoard, sortQueue, startModeOf, unreadNews,
} from './board'
import type { BoardSession, LiveSession } from '../../types'

const NOW = Date.parse('2026-10-30T19:10:00+01:00')
const OPTION = 'me_example.com'
const MASTER = `3-${OPTION}`

test('the header turns yellow from 2 h and red from 8 h', async () => {
  expect(freshness('2026-10-30T19:00:00+01:00', NOW)).toEqual({ label: '10 min', level: 'ok' })
  expect(freshness('2026-10-30T17:00:00+01:00', NOW)).toEqual({ label: '2 h 10 min', level: 'warn' })
  expect(freshness('2026-10-30T11:00:00+01:00', NOW)?.level).toBe('stale')
  expect(freshness(undefined, NOW)).toBeUndefined()
})

test('the queue shows the oldest ask first, its age in days', async () => {
  const sorted = sortQueue([{ id: 'a', since: '2026-10-30' }, { id: 'b', since: '2026-10-21' }, { id: 'c' }])
  expect(sorted.map(q => q.id)).toEqual(['b', 'a', 'c'])
  expect(ageDays('2026-10-21', NOW)).toBe(9)
  expect(ageDays('2026-10-30', NOW)).toBe(0)
  expect(ageDays(undefined, NOW)).toBeUndefined()
})

test('masters first, wait-owner on top, then priority with null last; workers under their parent, a parent without a role leads too', async () => {
  const s = (name: string, extra: Partial<BoardSession>): BoardSession => ({ name, ...extra })
  const groups = groupSessions([
    s('rust', { role: 'master', state: 'build' }),
    s('CTA', { role: 'master', state: 'build', priority: 1 }),
    s('chip', { role: 'worker', parent: 'CTA', state: 'ci' }),
    s('lat', { role: 'worker', parent: 'CTA', state: 'wait-owner' }),
    s('Nox', { role: 'master', state: 'wait-owner' }),
    s('Kiska', { role: 'worker', parent: null, state: 'idle' }),
    s('lead', {}),
    s('w', { parent: 'lead' }),
  ])
  expect(groups.map(g => g.head?.name ?? '-')).toEqual(['Nox', 'CTA', 'rust', 'lead', '-'])
  expect(groups[1]?.workers.map(w => w.name)).toEqual(['lat', 'chip'])
  expect(groups[3]?.workers.map(w => w.name)).toEqual(['w'])
  expect(groups[4]?.workers.map(w => w.name)).toEqual(['Kiska'])
})

test('the file parses with missing fields left out', async () => {
  const board = parseBoard('{"updated":"2026-10-30T18:10:00+01:00","sessions":[{"name":"x"}]}')
  expect(board.queue).toEqual([])
  expect(board.sessions[0]?.name).toBe('x')
  expect(board.updatedBy).toBeUndefined()
  expect([board.priorities, board.notes]).toEqual([undefined, undefined])
  expect(board.news).toEqual([])
})

test('news keeps items with an id and a title; an unknown kind is left out; a read item drops out', () => {
  const board = parseBoard(JSON.stringify({
    news: [
      { id: 'N1', title: ' Prod on v2.4.1 ', body: 'rollout done', ts: '2026-10-30', kind: 'gate' },
      { id: 'N2', title: 'Sign the agreement', kind: 'urgent' },
      { id: 'N3' },
      { title: 'no id' },
      'loose text',
    ],
  }))
  expect(board.news).toEqual([
    { id: 'N1', title: 'Prod on v2.4.1', body: 'rollout done', ts: '2026-10-30', kind: 'gate' },
    { id: 'N2', title: 'Sign the agreement', body: undefined, ts: undefined, kind: undefined },
  ])
  expect(parseBoard('{"news":"one string"}').news).toEqual([])
  const answers = lastAnswers([
    '{"id":"N1","answer":"read","ts":"2026-10-30T18:00:00Z","session":"lead"}',
    '{"id":"N2","answer":"discuss","ts":"2026-10-30T18:00:00Z"}',
  ].join('\n'))
  expect(unreadNews(board.news, answers).map(n => n.id)).toEqual(['N2'])
})

test('priorities as a list or one string make one line; notes is a trimmed string or nothing', () => {
  expect(parseBoard('{"priorities":["a"," b ",""],"notes":"  hold the release "}')).toMatchObject({ priorities: 'a · b', notes: 'hold the release' })
  expect(parseBoard('{"priorities":"one line","notes":"  "}')).toMatchObject({ priorities: 'one line', notes: undefined })
  expect(parseBoard('{"priorities":3,"notes":["x"]}')).toMatchObject({ priorities: undefined, notes: undefined })
})

test('the counter counts masters by lamp and every session in CI; a group rests when nobody in it runs or waits', () => {
  const sessions: BoardSession[] = [
    { name: 'a', role: 'master', state: 'build' },
    { name: 'b', role: 'master', state: 'wait-owner' },
    { name: 'c', role: 'master', state: 'idle' },
    { name: 'w', role: 'worker', parent: 'c', state: 'ci' },
    { name: 'd', state: 'done' },
  ]
  expect(countBoard(sessions)).toEqual({ masters: 3, runs: 1, waits: 1, quiet: 1, ci: 1 })
  const groups = groupSessions(sessions)
  expect(groups.map(g => [g.head?.name ?? '-', isResting(g)])).toEqual([['b', false], ['a', false], ['c', false], ['-', true]])
})

test('pack breaks between segments at the room, a wide one alone; clip ends in an ellipsis', () => {
  const w = (s: string) => s.length
  expect(pack(['aaaa', 'bb', 'cc', 'dddddddddd'], w, 8)).toEqual([['aaaa', 'bb'], ['cc'], ['dddddddddd']])
  expect(pack(['a', 'b'], w, 3, 1)).toEqual([['a', 'b']])
  expect([clip('abcdef', 4), clip('abc', 4)]).toEqual(['abc…', 'abc'])
})

test('with masterProfile set, the lamp names why a master is red, and a deviating mode yellow', async () => {
  const master: BoardSession = { name: 'onboarding', role: 'master' }
  const worker: BoardSession = { name: 'w', role: 'worker' }
  const live = (extra: Partial<LiveSession>): LiveSession => ({ envRead: true, mode: 'bypassPermissions', ...extra })

  expect(startModeOf(master, true, live({ weRole: 'master', profile: MASTER }), 'bypassPermissions', OPTION))
    .toEqual({ level: 'ok', reason: 'ok', mode: 'bypass' })
  const bare = startModeOf(master, true, live({}), 'bypassPermissions', OPTION)
  expect(bare.level).toBe('bad')
  expect(bare.reason).toBe('WE_ROLE missing — restart it as a master')
  // Unpinned: a master on the global login, outside the master profile, is fine.
  expect(startModeOf(master, true, live({ weRole: 'master', profile: '4-other_example.com' }), undefined, OPTION).level)
    .toBe('ok')
  expect(startModeOf(worker, false, live({ weRole: 'worker', profile: MASTER }), undefined, OPTION).reason)
    .toBe('worker in the master profile — it bills the master account')
  const auto = startModeOf(master, true, live({ weRole: 'master', profile: MASTER, mode: 'auto' }), 'bypassPermissions', OPTION)
  expect(auto).toEqual({ level: 'warn', reason: 'mode auto differs (most run bypass)', mode: 'auto' })
  expect(startModeOf(master, true, undefined, undefined, OPTION).level).toBe('none')
})

test('without masterProfile only the mode rule holds', async () => {
  const master: BoardSession = { name: 'm', role: 'master' }
  const worker: BoardSession = { name: 'w', role: 'worker' }
  const live = (extra: Partial<LiveSession>): LiveSession => ({ envRead: true, mode: 'bypassPermissions', ...extra })

  expect(startModeOf(master, true, live({}), 'bypassPermissions', undefined).level).toBe('ok')
  expect(startModeOf(worker, false, live({ weRole: 'worker', profile: MASTER }), 'bypassPermissions', undefined).level).toBe('ok')
  expect(startModeOf(master, true, live({ mode: 'default' }), 'bypassPermissions', undefined))
    .toEqual({ level: 'warn', reason: 'mode prompting differs (most run bypass)', mode: 'prompting' })
})

test('the master profile matches the account with or without the claude-swap number', async () => {
  expect(isMasterProfile(MASTER, OPTION)).toBe(true)
  expect(isMasterProfile(OPTION, OPTION)).toBe(true)
  expect(isMasterProfile('3-xme_example.com', OPTION)).toBe(false)
  expect(isMasterProfile(MASTER, undefined)).toBe(false)
})

test('a name running twice counts as its liveliest copy; the mode majority is counted', async () => {
  const map = liveByName([
    { name: 'Kiska', pid: 1, status: 'idle', mode: 'bypassPermissions' },
    { name: 'Kiska', pid: 2, status: 'busy', mode: 'bypassPermissions' },
    { name: 'paint', pid: null, state: 'blocked', mode: 'auto' },
  ])
  expect(map.get('Kiska')?.pid).toBe(2)
  expect(map.get('paint')?.liveness).toBe('blocked')
  expect(majorityMode(map.values())).toBe('bypassPermissions')
})

test('lastAnswers keeps the newest line per id and skips torn ones', () => {
  const text = [
    '{"id":"Q1","answer":"discuss","ts":"2026-10-30T18:00:00Z","session":"lead"}',
    '{"id":"Q1","answer":"accept","ts":"2026-10-30T18:05:00Z"}',
    '{"id":"Q2","answer":"yes","ts":"x"}',
    '{"id":"Q5","answer":"deny","ts":"2026-10-30T18:06:00Z","session":"lead"}',
    '{"id":"Q3",',
    '',
  ].join('\n')
  expect(lastAnswers(text)).toEqual({
    Q1: { id: 'Q1', answer: 'accept', ts: '2026-10-30T18:05:00Z', session: null },
    Q5: { id: 'Q5', answer: 'deny', ts: '2026-10-30T18:06:00Z', session: 'lead' },
  })
})

test('the answers file sits beside the board file; ownName matches on the session id', () => {
  expect(answersPathOf('/home/me/.claude/we-state/board.json')).toBe('/home/me/.claude/we-state/board-answers.jsonl')
  expect(answersPathOf('/home/me/boards/team.json')).toBe('/home/me/boards/board-answers.jsonl')
  const live = [{ name: 'lead', sessionId: 'a' }, { name: null, sessionId: 'b' }, { name: 'Orchestrator', sessionId: 'c' }]
  expect(ownName(live, 'c')).toBe('Orchestrator')
  expect(ownName(live, 'b')).toBeUndefined()
  expect(answerPrompt('discuss', 'Q4')).toBe("Q4: let's talk about it")
  expect(answerPrompt('deny', 'Q4')).toBe('Q4: proposal denied')
  expect(answerPrompt('deny', 'Q4', parseBoard('{"answer_prompts":{"deny":"{id}: abgelehnt","read":"x"}}').answerPrompts)).toBe('Q4: abgelehnt')
  const own = parseBoard(JSON.stringify({ answer_prompts: { accept: '{id}: Vorschlag angenommen', info: 7 } })).answerPrompts
  expect(answerPrompt('accept', 'Q4', own)).toBe('Q4: Vorschlag angenommen')
  expect(answerPrompt('info', 'Q4', own)).toBe('Q4: I need more information')
})
