// /flow: a pane with a traffic light per /we:master step for a story, an epic's stories, or
// what this session works on; in a master everything it orchestrates (master.ts), so the human
// sees it there instead of asking. Reads git and gh itself; no agent feeds it.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, PluginOptions, Register } from 'claude-code'

type On = Parameters<Register>[0]

import type { FlowGroup, FlowLight, FlowPhase, FlowRow, FlowView } from '../../types'
import { openBoard } from '../board/register'
import { defaultBranch, git, loadPrs, planGrep } from '../plans/plans'
import { crewFlowLines, loadCrewFlow, readCrewFlow } from './crewflow'
import { PHASE_COLOR as COLOR, PHASE_URGENCY as URGENCY, keysIn, matchesKey, parsePlans, phaseOf, stagesOf } from './phase'
import type { Plan } from './phase'
import { masterKeys, masterView, otherWorkersLine, workerLine } from './master'
import type { MasterOrchestration } from './master'

const PANE = 'we-flow'
const REFRESH_MS = 120_000
const MAX_KEYS = 6
const LAST_KEYS = 'flow.lastKeys'
// The master record of a view whose source is `master <name>` (FlowView's type lies in types/).
const MASTER = 'flow.master'
const isMasterSource = (source?: string) => !!source?.startsWith('master ')
const view = atom({ plugin: 'we', key: 'flowBoard' } as const, null)

const LABEL: Record<FlowPhase, string> = {
  idea: 'no plan',
  draft: 'plan draft',
  refined: 'ready to build',
  dev: 'in development',
  ci: 'CI running',
  'ci-red': 'CI red',
  ready: 'CI green · waiting for merge',
  merged: 'merged',
  closed: 'PR closed',
}

const LAMP: Record<FlowLight, { glyph: string; color: string }> = {
  done: { glyph: '●', color: 'success' },
  active: { glyph: '◉', color: 'warning' },
  red: { glyph: '◉', color: 'error' },
  todo: { glyph: '○', color: 'inactive' },
  skip: { glyph: '–', color: 'inactive' },
}

type $ = EngineInterface
let isRefreshing = false

const lines = (out: string) => out.split('\n').map(l => l.trim()).filter(Boolean)

async function repoTop($: $): Promise<string> {
  const top = (await $.process.run(['git', 'rev-parse', '--show-toplevel'])).stdout.trim()
  if (!top) throw new Error('this session runs in no git repository')
  return top
}

// The ticket prefix /we:setup wrote (`ticketing.project_key`), so `feat/proj-12-x` reads as PROJ-12.
async function projectKey($: $, top: string): Promise<string | undefined> {
  try {
    const config = JSON.parse(String(await $.fs.read(`${top}/.weside/config.json`))) as { ticketing?: { project_key?: string } }
    return config.ticketing?.project_key || undefined
  } catch {
    return undefined
  }
}

async function gather($: $, keys: string[], master?: MasterOrchestration): Promise<FlowGroup[]> {
  const top = await repoTop($)
  await git($, top, ['fetch', 'origin', '--quiet'], 60_000)
  const base = await defaultBranch($, top)
  const strip = (hit: string) => hit.slice(base.length + 1)

  const groups: { key: string; stem?: string; epicTitle?: string; storyKeys: string[]; paths: string[] }[] = []
  for (const key of keys) {
    const epicHit = lines(await git($, top, ['grep', '-l', '-E', `^ticket: ${key}$`, base, '--', 'docs/plans/*epic*.md']))[0]
    const ordered = master?.epic === key ? master.stories.map(s => s.key) : []
    if (!epicHit && ordered.length) {
      // A master's epic whose plan lies in another repo: an epic group of the stories it orchestrates.
      groups.push({ key, epicTitle: key, storyKeys: ordered, paths: ordered.map(k => `docs/plans/${k}-story.md`) })
      continue
    }
    if (!epicHit) {
      groups.push({ key, storyKeys: [key], paths: [`docs/plans/${key}-story.md`] })
      continue
    }
    const epicPath = strip(epicHit)
    const stem = epicPath.replace(/^docs\/plans\//, '').replace(/-epic\.md$/, '')
    const heading = lines(await git($, top, ['grep', '-h', '-m1', '-e', '^# ', base, '--', epicPath]))[0]
    // A story names its epic by the ticket key or, without ticketing, by the epic's file stem (epic-plan.md § Links).
    const paths = lines(await git($, top, ['grep', '-l', '-E', `^epic: (${key}|${stem})$`, base, '--', 'docs/plans/*-story.md'])).map(strip)
    groups.push({ key, stem, epicTitle: heading?.replace(/^#\s*(Epic:\s*)?/, '') ?? key, storyKeys: [], paths })
  }

  const allPaths = [...new Set(groups.flatMap(g => g.paths))]
  const plans: Plan[] = allPaths.length
    ? parsePlans(await git($, top, planGrep(base, allPaths)))
    : []
  for (const group of groups) {
    if (group.epicTitle === undefined) continue
    const fromPlans = plans.filter(p => p.epic === group.key || p.epic === group.stem).map(p => p.key)
    const fromMaster = master?.epic === group.key ? master.stories.map(s => s.key) : []
    group.storyKeys = [...new Set([...(group.stem === undefined ? group.storyKeys : []), ...fromPlans, ...fromMaster])]
  }

  const allKeys = [...new Set(groups.flatMap(g => g.storyKeys))]
  const refs = lines(await git($, top, ['for-each-ref', '--format=%(refname:short)', 'refs/heads', 'refs/remotes/origin']))
  const worktrees = new Map<string, string>()
  let wtPath = ''
  for (const line of lines(await git($, top, ['worktree', 'list', '--porcelain']))) {
    if (line.startsWith('worktree ')) wtPath = line.slice(9)
    if (line.startsWith('branch refs/heads/')) worktrees.set(line.slice(18), wtPath)
  }
  const prs = await loadPrs($, top, allKeys)

  const rowOf = async (key: string): Promise<FlowRow> => {
    const plan = plans.find(p => p.key === key)
    const mine = prs.filter(pr => matchesKey(pr.headRefName, key) || matchesKey(pr.title, key))
    const aheadBranches: string[] = []
    let ahead = 0
    for (const ref of refs.filter(r => matchesKey(r, key) && r !== 'origin/HEAD')) {
      const count = Number((await git($, top, ['rev-list', '--count', `${base}..${ref}`])).trim())
      if (count > 0) aheadBranches.push(ref.replace(/^origin\//, ''))
      ahead = Math.max(ahead, count)
    }
    const open = mine.find(p => p.state === 'OPEN')
    const branch = open?.headRefName ?? aheadBranches[0]
    const pr = open ?? mine.find(p => p.state === 'MERGED') ?? mine[0]
    const evidence = { plan, prs: mine, aheadBranches }
    return {
      key,
      title: plan?.title || pr?.title || '',
      phase: phaseOf(evidence),
      stages: stagesOf({ ...evidence, ahead, branch }),
      pr: pr?.number,
      epic: plan?.epic,
      branch,
      worktree: branch ? worktrees.get(branch) : undefined,
    }
  }

  const out: FlowGroup[] = []
  for (const group of groups) {
    const rows: FlowRow[] = []
    for (const key of group.storyKeys) rows.push(await rowOf(key))
    rows.sort((a, b) => URGENCY[a.phase] - URGENCY[b.phase] || a.key.localeCompare(b.key))
    out.push({ key: group.key, epicTitle: group.epicTitle, rows })
  }
  return out
}

// /flow with no key: in a master what it orchestrates, else what this session works on, the most
// specific source first.
async function detect($: $): Promise<{ keys: string[]; source: string; master?: MasterOrchestration } | undefined> {
  const master = await masterView($)
  if (master && masterKeys(master).length) return { keys: masterKeys(master), source: `master ${master.name}`, master }
  const top = await repoTop($).catch(() => undefined)
  const prefix = top ? await projectKey($, top) : undefined
  const home = await $.env.get('HOME')
  const id = await $.session.id()
  if (home) {
    try {
      // The statusline focus /we:master writes when it pushes (§ Push, PR, CI).
      const focus = JSON.parse(String(await $.fs.read(`${home}/.claude/we-focus/${id}.json`))) as { branch?: string }
      const keys = keysIn(focus.branch ?? '', prefix)
      if (keys.length) return { keys: keys.slice(0, 1), source: `focus ${focus.branch}` }
    } catch {
      // No focus file for this session: fall through to the branch.
    }
  }
  const branch = (await $.process.run(['git', 'branch', '--show-current'])).stdout.trim()
  const fromBranch = keysIn(branch, prefix)
  if (fromBranch.length) return { keys: fromBranch.slice(0, 1), source: `branch ${branch}` }

  // Only what the person typed and the skills run on a key: Claude's own prose names example keys.
  const said: string[] = []
  for (const message of await $.session.messages()) {
    if (message.role === 'user') said.push(...keysIn(message.text.replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, ''), prefix))
    for (const use of message.toolUses) if (use.tool === 'Skill') said.push(...keysIn(JSON.stringify(use.input), prefix))
  }
  // Newest mention first, each key once.
  const recent = [...new Set(said.reverse())].slice(0, MAX_KEYS)
  if (recent.length) return { keys: recent, source: 'conversation' }

  const last = await $.store.get(LAST_KEYS)
  return Array.isArray(last) && last.length ? { keys: last.map(String), source: 'last viewed' } : undefined
}

const allRows = (v: FlowView) => v.groups.flatMap(g => g.rows)

const summary = (v: FlowView): string => {
  const rows = allRows(v)
  const merged = rows.filter(r => r.phase === 'merged').length
  const red = rows.filter(r => r.phase === 'ci-red' || r.phase === 'closed').length
  const active = rows.length - merged - red
  return [`${merged}/${rows.length} merged`, active && `${active} open`, red && `${red} red`].filter(Boolean).join(' · ')
}

const title = (keys: string[]) => `Flow ${keys.join(' ')}`

async function refresh($: $, keys: string[], source?: string, fresh?: MasterOrchestration) {
  if (isRefreshing) return
  isRefreshing = true
  try {
    await update($, view, v =>
      v && v.keys.join() === keys.join() ? { ...v, isLoading: true } : { keys, source, groups: [], updatedAt: 0, isLoading: true },
    )
    // A master view re-reads its workers with the timer; a failed re-read keeps the last record.
    // A good re-read also renews the keys: a master gains stories, or an epic, after the open.
    let master: MasterOrchestration | undefined
    if (isMasterSource(source)) {
      const reread = fresh ?? (await masterView($))
      master = reread ?? ((await $.store.get(MASTER)) as MasterOrchestration | undefined)
      if (reread) {
        await $.store.set(MASTER, reread)
        if (masterKeys(reread).length) keys = masterKeys(reread)
      }
    }
    const groups = await gather($, keys, master)
    const next: FlowView = { keys, source, groups, updatedAt: await $.clock.now(), isLoading: false }
    await update($, view, () => next)
    await $.store.set(LAST_KEYS, keys)
    $.ui.status(`${keys.join(' ')}: ${summary(next)}`)
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err)
    $.ui.log(`flow: fetch for ${keys.join(' ')} failed: ${error}`)
    await update($, view, v => ({ ...(v ?? { groups: [], updatedAt: 0 }), keys, source, isLoading: false, error }))
  } finally {
    isRefreshing = false
  }
}

// The fetch outlives the command or press that asked for it: a timer runs outside that dispatch.
function later($: $, keys: string[], source?: string, master?: MasterOrchestration) {
  $.clock.after(0, () => void refresh($, keys, source, master))
}

// A button's slash command, queued as if the person typed it; it runs once the session is idle.
async function runCommand($: $, command: string, args: string) {
  try {
    await $.command.run({ command, args })
  } catch (err) {
    $.ui.toast(`/${command} ${args}: ${err instanceof Error ? err.message : String(err)}`)
  }
}

const clip = (text: string, room: number) => (text.length > room ? `${text.slice(0, Math.max(0, room - 1))}…` : text)

const bar = (done: number, total: number, width: number) => {
  const filled = total ? Math.round((done / total) * width) : 0
  return { filled: '█'.repeat(filled), empty: '░'.repeat(width - filled) }
}

// Run from the module's one session.start hook (hooks/register.ts); everything it reaches with $
// is a function declaration, the only form the engine follows past an import.
export async function startFlow($: $) {
  await $.command.register({
    name: 'flow',
    description: "Traffic lights per /we:master step for a story or an epic; no key: a master's orchestration, else what this session works on",
    argumentHint: '[KEY …]',
  })
  const current = await read($, view)
  if (current) void $.ui.open({ id: PANE, title: title(current.keys) })
  $.clock.every(REFRESH_MS, () => {
    void read($, view).then(v => v && refresh($, v.keys, v.source))
    void readCrewFlow($).then(c => c && loadCrewFlow($))
  })
}

// /flow's work, also the board pane's Flow button: a plugin's own $.command.run does not reach its own hook.
export async function openFlow($: $, args: string): Promise<string> {
  const asked = keysIn(args.toUpperCase()).slice(0, MAX_KEYS)
  const found = asked.length ? { keys: asked, source: undefined } : await detect($)
  // Crew flow first: read from the last snapshot, so it shows within the press.
  await loadCrewFlow($)
  if (!found) {
    const opened = await $.ui.open({ id: PANE, title: 'Flow' })
    if (!opened.isPlaced) return `Flow pane waits undrawn: ${opened.reason}`
    return 'Flow pane opened with Crew flow; no ticket key found in this session for the story lights (/flow PROJ-123).'
  }
  const opened = await $.ui.open({ id: PANE, title: title(found.keys) })
  later($, found.keys, found.source, 'master' in found ? found.master : undefined)
  const from = found.source ? ` (from ${found.source})` : ''
  if (!opened.isPlaced) return `Flow pane for ${found.keys.join(' ')}${from} waits undrawn: ${opened.reason}`
  return `Flow pane for ${found.keys.join(' ')}${from} opened.`
}

export const registerFlow = (on: On, options: PluginOptions) => {
  on('command.run', { command: 'flow' }, async ($, e) => ({ text: await openFlow($, e.args) }))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const v = await read($, view)
    const width = Math.max(30, e.props.bodyColumns ?? e.viewport?.columns ?? 80)
    const crew = await readCrewFlow($)
    const now = await $.clock.now()
    const crewSection = crew && (
      <Box flexDirection="column" borderStyle="round" borderColor="claude" paddingX={1}>
        {crewFlowLines(crew, now).map(line => (
          <Text color={line.color} dimColor={line.dim} bold={line.bold}>{clip(line.text, width - 4)}</Text>
        ))}
      </Box>
    )
    if (!v) {
      return (
        <Box flexDirection="column" gap={1}>
          {crewSection}
          <Text dimColor>/flow shows what this session works on, in a master all it orchestrates so you see it instead of asking; /flow PROJ-123 a story or an epic.</Text>
        </Box>
      )
    }

    const master = isMasterSource(v.source) ? ((await $.store.get(MASTER)) as MasterOrchestration | undefined) : undefined
    const workersOf = (key: string) =>
      (master?.stories.find(s => s.key === key)?.workers ?? []).map(w => <Text dimColor>{clip(workerLine(w), width - 6)}</Text>)
    const others = master && otherWorkersLine(master)

    const rows = allRows(v)
    const merged = rows.filter(r => r.phase === 'merged').length
    const progress = bar(merged, rows.length, Math.min(30, width - 16))
    const stamp = v.updatedAt ? new Date(v.updatedAt).toISOString().slice(11, 16) + ' UTC' : '–'

    const action = (key: string, label: string, command: string, args: string) => (
      <Button key={key} label={label} onPress={() => runCommand($, command, args)} />
    )

    // The next step per /we:master § State per story, as a button that runs it.
    const actionsOf = (row: FlowRow) => {
      const stages = row.stages ?? []
      const lit = (name: string) => stages.find(s => s.name === name)?.light
      if (row.phase === 'merged') return []
      const out = [action(`${row.key}-standup`, 'Standup', 'we:standup', row.key)]
      if (lit('Plan') === 'active' || lit('Approval') === 'active') out.push(action(`${row.key}-refine`, 'Refine', 'we:master', row.key))
      else if (lit('Build') === 'todo' && lit('Approval') === 'done') out.push(action(`${row.key}-build`, 'Build', 'we:master', row.key))
      if (row.pr && (lit('CI') === 'red' || lit('Review') === 'red' || lit('Merge') === 'red')) {
        out.push(action(`${row.key}-ci`, 'Fix CI', 'we:ci-review', String(row.pr)))
      }
      return out
    }

    const lamps = (row: FlowRow) =>
      (row.stages ?? []).map(stage => (
        <Text>
          <Text color={LAMP[stage.light].color} bold={stage.light !== 'todo' && stage.light !== 'skip'}>{LAMP[stage.light].glyph}</Text>
          <Text color={stage.light === 'todo' || stage.light === 'skip' ? 'inactive' : undefined}>{` ${stage.name}  `}</Text>
        </Text>
      ))

    const details = (row: FlowRow) =>
      (row.stages ?? [])
        .filter(stage => stage.note && stage.light !== 'todo')
        .map(stage => (
          <Text>
            <Text color={LAMP[stage.light].color}>{`${LAMP[stage.light].glyph} ${stage.name.padEnd(9)}`}</Text>
            <Text dimColor={stage.light === 'done' || stage.light === 'skip'}>{clip(stage.note, width - 16)}</Text>
          </Text>
        ))

    const card = (row: FlowRow, isSolo: boolean) => (
      <Box flexDirection="column" borderStyle="round" borderColor={COLOR[row.phase]} paddingX={1}>
        <Text>
          <Text bold>{row.key}</Text>
          <Text color={COLOR[row.phase]} bold>{`  ${LABEL[row.phase]}`}</Text>
          {row.pr && <Text dimColor>{`  #${row.pr}`}</Text>}
          {isSolo && row.epic && <Text dimColor>{`  · epic ${row.epic}`}</Text>}
        </Text>
        {row.title && <Text>{clip(row.title, width - 6)}</Text>}
        <Box flexDirection="row" flexWrap="wrap">{lamps(row)}</Box>
        <Box flexDirection="column" marginTop={1}>{details(row)}</Box>
        {row.worktree && <Text dimColor>{'↳ ' + clip(row.worktree, width - 8)}</Text>}
        {workersOf(row.key)}
        <Box flexDirection="row" gap={1} marginTop={1}>{actionsOf(row)}</Box>
      </Box>
    )

    const doneLine = (row: FlowRow) => (
      <Box flexDirection="column">
        <Text>
          <Text color="success">{'✓ '}</Text>
          <Text dimColor>{`${row.key}  ${clip(row.title, width - row.key.length - 14)}`}</Text>
          {row.pr && <Text dimColor>{`  #${row.pr}`}</Text>}
        </Text>
        {workersOf(row.key)}
      </Box>
    )

    return (
      <Box flexDirection="column" gap={1}>
        {crewSection}
        <Box flexDirection="column">
          <Box flexDirection="row" gap={2}>
            <Text bold>{`◆ ${v.keys.join(' · ')}`}</Text>
            <Button key="board" label="Board" onPress={() => void openBoard($, options, false)} />
          </Box>
          {v.source && <Text dimColor>{`detected from ${v.source}`}</Text>}
          {master && !master.crewRepo && (
            <Text color="warning">{clip(`${v.source}: no crew repo found — stories from the board line`, width - 2)}</Text>
          )}
          {rows.length > 0 && (
            <Text>
              <Text color="success">{progress.filled}</Text>
              <Text color="inactive">{progress.empty}</Text>
              <Text bold>{`  ${summary(v)}`}</Text>
            </Text>
          )}
          {v.error && <Text color="error">{`Error: ${v.error}`}</Text>}
          {v.isLoading && rows.length === 0 && <Text dimColor>reading git and GitHub …</Text>}
        </Box>

        {v.groups.map(group => {
          // A story asked for on its own is always a card, merged or not; in an epic merged ones fold to a line.
          const isSolo = group.epicTitle === undefined
          const open = group.rows.filter(r => isSolo || r.phase !== 'merged')
          const done = group.rows.filter(r => !isSolo && r.phase === 'merged')
          return (
            <Box flexDirection="column">
              {group.epicTitle !== undefined && (
                <Box flexDirection="column">
                  <Text>
                    <Text color="claude" bold>{`Epic ${group.key}`}</Text>
                    <Text dimColor>{`  ${clip(group.epicTitle, width - group.key.length - 8)}`}</Text>
                  </Text>
                  <Box flexDirection="row" gap={1}>
                    {action(`${group.key}-standup`, 'Standup', 'we:standup', group.key)}
                    {action(`${group.key}-epic`, 'Epic status', 'we:epic', group.key)}
                    {open.length > 0 && action(`${group.key}-master`, 'Master', 'we:master', group.key)}
                  </Box>
                </Box>
              )}
              {group.rows.length === 0 && !v.isLoading && <Text dimColor>No story plans on the default branch.</Text>}
              {open.map(row => card(row, isSolo))}
              {done.length > 0 && (
                <Box flexDirection="column" marginTop={open.length ? 1 : 0}>
                  {done.map(doneLine)}
                </Box>
              )}
            </Box>
          )
        })}
        {others && <Text dimColor>{clip(others, width - 2)}</Text>}

        <Box flexDirection="row" gap={2}>
          <Button key="refresh" hotkey="r" label={v.isLoading ? 'loading…' : 'Refresh'} onPress={() => later($, v.keys, v.source)} />
          <Text dimColor>{`as of ${stamp} · every 2 min · git + GitHub`}</Text>
        </Box>
        <Text dimColor>
          <Text color="success">●</Text>
          {' done  '}
          <Text color="warning">◉</Text>
          {' current  '}
          <Text color="error">◉</Text>
          {' stuck  '}
          <Text color="inactive">○</Text>
          {' open  '}
          <Text color="inactive">–</Text>
          {' skipped'}
        </Text>
      </Box>
    )
  })
}
