import { expect, test } from 'claude-code/testing'

import { BOARD_TEXT_MAX, crewFlowLines } from './crewflow'
import type { CrewFlowView } from '../../types'

const NOW = Date.parse('2026-11-27T10:00:00Z')
const view = (now: CrewFlowView['now']): CrewFlowView => ({
  generatedAt: '2026-11-27T09:59:00Z',
  now,
  ci: [],
  gaps: [],
  isRefreshing: false,
})

test('a session with a board line shows its topic and now below its line, dim and cut', async () => {
  const long = `27.11. Stufe 1 Gruppe 1 (Plan und Geld): Probedurchgang Home wird vorbereitet ${'x'.repeat(200)}`
  const lines = crewFlowLines(
    view([{ who: 'amir', kind: 'working', since: '2026-11-27T09:00:00Z', topic: 'ABC-7 UX tune', board_now: long }]),
    NOW,
  )
  const at = lines.findIndex(l => l.text.startsWith('amir  works'))
  expect(lines[at + 1]).toEqual({ text: '    ABC-7 UX tune', dim: true })
  expect(lines[at + 2].dim).toBe(true)
  expect(lines[at + 2].text.startsWith('    27.11. Stufe 1')).toBe(true)
  expect(lines[at + 2].text.endsWith('…')).toBe(true)
  expect(lines[at + 2].text.length).toBe(4 + BOARD_TEXT_MAX)
})

test('a session without a board line or its fields keeps its one line', async () => {
  const rows = [
    { who: 'w-1', kind: 'working', since: '2026-11-27T09:00:00Z' },
    { who: 'w-2', kind: 'working', since: '2026-11-27T09:00:00Z', topic: null, board_now: '  ' },
  ]
  const lines = crewFlowLines(view(rows), NOW)
  expect(lines.map(l => l.text.slice(0, 5))).toEqual(['Crew ', 'w-1  ', 'w-2  '])
})
