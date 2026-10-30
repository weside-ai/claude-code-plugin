import { expect, test } from 'claude-code/testing'

import { ageDays, freshness, groupSessions, isMasterProfile, liveByName, majorityMode, parseBoard, sortQueue, startModeOf } from './board'
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

test('masters first, wait-owner on top, then priority with null last; workers under their parent', async () => {
  const s = (name: string, extra: Partial<BoardSession>): BoardSession => ({ name, ...extra })
  const groups = groupSessions([
    s('rust', { role: 'master', state: 'build' }),
    s('CTA', { role: 'master', state: 'build', priority: 1 }),
    s('chip', { role: 'worker', parent: 'CTA', state: 'ci' }),
    s('lat', { role: 'worker', parent: 'CTA', state: 'wait-owner' }),
    s('Nox', { role: 'master', state: 'wait-owner' }),
    s('Kiska', { role: 'worker', parent: null, state: 'idle' }),
  ])
  expect(groups.map(g => g.head?.name ?? '-')).toEqual(['Nox', 'CTA', 'rust', '-'])
  expect(groups[1]?.workers.map(w => w.name)).toEqual(['lat', 'chip'])
  expect(groups[3]?.workers.map(w => w.name)).toEqual(['Kiska'])
})

test('the file parses with missing fields left out', async () => {
  const board = parseBoard('{"updated":"2026-10-30T18:10:00+01:00","sessions":[{"name":"x"}]}')
  expect(board.queue).toEqual([])
  expect(board.sessions[0]?.name).toBe('x')
  expect(board.updatedBy).toBeUndefined()
})

test('with masterProfile set, the lamp names why a master is red, and a deviating mode yellow', async () => {
  const master: BoardSession = { name: 'onboarding', role: 'master' }
  const worker: BoardSession = { name: 'w', role: 'worker' }
  const live = (extra: Partial<LiveSession>): LiveSession => ({ envRead: true, mode: 'bypassPermissions', ...extra })

  expect(startModeOf(master, true, live({ weRole: 'master', profile: MASTER }), 'bypassPermissions', OPTION))
    .toEqual({ level: 'ok', reason: 'ok', mode: 'bypass' })
  const bare = startModeOf(master, true, live({}), 'bypassPermissions', OPTION)
  expect(bare.level).toBe('bad')
  expect(bare.reason).toBe('WE_ROLE missing · not in the master profile — restart it as a master')
  expect(startModeOf(master, true, live({ weRole: 'master', profile: '4-other_example.com' }), undefined, OPTION).reason)
    .toBe('profile 4-other_example.com, not the master profile — restart it as a master')
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
