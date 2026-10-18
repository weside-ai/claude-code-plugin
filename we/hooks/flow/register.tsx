// /flow: a pane with a traffic light per /we:orchestrate step for a story, an epic's stories, or
// what this session works on. Reads git and gh itself; no agent feeds it.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { FlowGroup, FlowLight, FlowPhase, FlowRow, FlowView } from '../../types'
import { keysIn, matchesKey, parsePlans, phaseOf, stagesOf } from './phase'
import type { Plan, Pr } from './phase'

const PANE = 'we-flow'
const REFRESH_MS = 120_000
const MAX_KEYS = 6
const LAST_KEYS = 'flow.lastKeys'
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

const COLOR: Record<FlowPhase, string> = {
  idea: 'inactive',
  draft: 'warning',
  refined: 'suggestion',
  dev: 'warning',
  ci: 'warning',
  'ci-red': 'error',
  ready: 'success',
  merged: 'merged',
  closed: 'error',
}

const LAMP: Record<FlowLight, { glyph: string; color: string }> = {
  done: { glyph: '●', color: 'success' },
  active: { glyph: '◉', color: 'warning' },
  red: { glyph: '◉', color: 'error' },
  todo: { glyph: '○', color: 'inactive' },
  skip: { glyph: '–', color: 'inactive' },
}

// Open work first, the most urgent on top.
const URGENCY: Record<FlowPhase, number> = {
  'ci-red': 0, closed: 1, ci: 2, ready: 3, dev: 4, refined: 5, draft: 6, idea: 7, merged: 8,
}

type $ = EngineInterface
let isRefreshing = false

const git = async ($: $, cwd: string, argv: string[], timeoutMs = 30_000): Promise<string> => {
  const run = await $.process.run(['git', ...argv], { cwd, timeoutMs })
  // git grep answers 1 for "no match", which is a valid empty answer here.
  if (run.exitCode !== 0 && !(argv[0] === 'grep' && run.exitCode === 1)) {
    throw new Error(`git ${argv[0]}: ${run.stderr.trim().split('\n')[0] ?? run.exitCode}`)
  }
  return run.stdout
}

const lines = (out: string) => out.split('\n').map(l => l.trim()).filter(Boolean)

const loadPrs = async ($: $, cwd: string, keys: string[]): Promise<Pr[]> => {
  const prs: Pr[] = []
  // GitHub search takes at most five boolean operators per query.
  for (let i = 0; i < keys.length; i += 6) {
    const run = await $.process.run(
      [
        'gh', 'pr', 'list', '--state', 'all', '--limit', '100',
        '--search', keys.slice(i, i + 6).join(' OR '),
        '--json', 'number,state,headRefName,title,autoMergeRequest,statusCheckRollup,mergeStateStatus,isDraft',
      ],
      { cwd, timeoutMs: 30_000 },
    )
    if (run.exitCode !== 0) throw new Error(`gh pr list: ${run.stderr.trim().split('\n')[0]}`)
    prs.push(...(JSON.parse(run.stdout) as Pr[]))
  }
  return prs
}

const repoTop = async ($: $): Promise<string> => {
  const top = (await $.process.run(['git', 'rev-parse', '--show-toplevel'])).stdout.trim()
  if (!top) throw new Error('this session runs in no git repository')
  return top
}

// The ticket prefix /we:setup wrote (`ticketing.project_key`), so `feat/proj-12-x` reads as PROJ-12.
const projectKey = async ($: $, top: string): Promise<string | undefined> => {
  try {
    const config = JSON.parse(String(await $.fs.read(`${top}/.weside/config.json`))) as { ticketing?: { project_key?: string } }
    return config.ticketing?.project_key || undefined
  } catch {
    return undefined
  }
}

const defaultBranch = async ($: $, top: string): Promise<string> => {
  const head = await $.process.run(['git', 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD'], { cwd: top })
  return head.exitCode === 0 && head.stdout.trim() ? head.stdout.trim() : 'origin/main'
}

const gather = async ($: $, keys: string[]): Promise<FlowGroup[]> => {
  const top = await repoTop($)
  await git($, top, ['fetch', 'origin', '--quiet'], 60_000)
  const base = await defaultBranch($, top)
  const strip = (hit: string) => hit.slice(base.length + 1)

  const groups: { key: string; stem?: string; epicTitle?: string; storyKeys: string[]; paths: string[] }[] = []
  for (const key of keys) {
    const epicHit = lines(await git($, top, ['grep', '-l', '-E', `^ticket: ${key}$`, base, '--', 'docs/plans/*epic*.md']))[0]
    if (!epicHit) {
      groups.push({ key, storyKeys: [key], paths: [`docs/plans/${key}-story.md`] })
      continue
    }
    const epicPath = strip(epicHit)
    const stem = epicPath.replace(/^docs\/plans\//, '').replace(/-epic\.md$/, '')
    const heading = lines(await git($, top, ['grep', '-h', '-m1', '-e', '^# ', base, '--', epicPath]))[0]
    // A story names its epic by the ticket key or, without ticketing, by the epic's file stem (apo-hierarchy.md).
    const paths = lines(await git($, top, ['grep', '-l', '-E', `^epic: (${key}|${stem})$`, base, '--', 'docs/plans/*-story.md'])).map(strip)
    groups.push({ key, stem, epicTitle: heading?.replace(/^#\s*(Epic:\s*)?/, '') ?? key, storyKeys: [], paths })
  }

  const allPaths = [...new Set(groups.flatMap(g => g.paths))]
  const plans: Plan[] = allPaths.length
    ? parsePlans(await git($, top, ['grep', '-E', '-e', '^(story|status|epic):', '-e', '^# ', base, '--', ...allPaths]))
    : []
  for (const group of groups) {
    if (group.epicTitle === undefined) continue
    group.storyKeys = [...new Set(plans.filter(p => p.epic === group.key || p.epic === group.stem).map(p => p.key))]
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

// /flow with no key: what this session works on, the most specific source first.
const detect = async ($: $): Promise<{ keys: string[]; source: string } | undefined> => {
  const top = await repoTop($).catch(() => undefined)
  const prefix = top ? await projectKey($, top) : undefined
  const home = await $.env.get('HOME')
  const id = await $.session.id()
  if (home) {
    try {
      // The statusline focus /we:orchestrate writes when it pushes (§ Push, PR, CI).
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

const refresh = async ($: $, keys: string[], source?: string) => {
  if (isRefreshing) return
  isRefreshing = true
  try {
    await update($, view, v =>
      v && v.keys.join() === keys.join() ? { ...v, isLoading: true } : { keys, source, groups: [], updatedAt: 0, isLoading: true },
    )
    const groups = await gather($, keys)
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
const later = ($: $, keys: string[], source?: string) => {
  $.clock.after(0, () => void refresh($, keys, source))
}

// A button's slash command, queued as if the person typed it; it runs once the session is idle.
const runCommand = async ($: $, command: string, args: string) => {
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

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'flow',
      description: 'Traffic lights per /we:orchestrate step for a story or an epic; no key: what this session works on',
      argumentHint: '[KEY …]',
    })
    const current = await read($, view)
    if (current) void $.ui.open({ id: PANE, title: title(current.keys) })
    $.clock.every(REFRESH_MS, () => {
      void read($, view).then(v => v && refresh($, v.keys, v.source))
    })
    return next(e)
  })

  on('command.run', { command: 'flow' }, async ($, e) => {
    const asked = keysIn(e.args.toUpperCase()).slice(0, MAX_KEYS)
    const found = asked.length ? { keys: asked, source: undefined } : await detect($)
    if (!found) return { text: 'No ticket key found in this session. Usage: /flow PROJ-123 (a story or an epic)' }
    const opened = await $.ui.open({ id: PANE, title: title(found.keys) })
    later($, found.keys, found.source)
    const from = found.source ? ` (from ${found.source})` : ''
    if (!opened.isPlaced) return { text: `Flow pane for ${found.keys.join(' ')}${from} waits undrawn: ${opened.reason}` }
    return { text: `Flow pane for ${found.keys.join(' ')}${from} opened.` }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const v = await read($, view)
    const width = Math.max(30, e.props.bodyColumns ?? e.viewport?.columns ?? 80)
    if (!v) return <Text dimColor>/flow shows what this session works on; /flow PROJ-123 a story or an epic.</Text>

    const rows = allRows(v)
    const merged = rows.filter(r => r.phase === 'merged').length
    const progress = bar(merged, rows.length, Math.min(30, width - 16))
    const stamp = v.updatedAt ? new Date(v.updatedAt).toISOString().slice(11, 16) + ' UTC' : '–'

    const action = (key: string, label: string, command: string, args: string) => (
      <Button key={key} label={label} onPress={() => runCommand($, command, args)} />
    )

    // The next step per /we:orchestrate § State per story, as a button that runs it.
    const actionsOf = (row: FlowRow) => {
      const stages = row.stages ?? []
      const lit = (name: string) => stages.find(s => s.name === name)?.light
      const out = [action(`${row.key}-standup`, 'Standup', 'we:standup', row.key)]
      if (lit('Plan') === 'active' || lit('Approval') === 'active') out.push(action(`${row.key}-refine`, 'Refine', 'we:orchestrate', row.key))
      else if (lit('Build') === 'todo' && lit('Approval') === 'done') out.push(action(`${row.key}-build`, 'Build', 'we:orchestrate', row.key))
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

    const openCard = (row: FlowRow) => (
      <Box flexDirection="column" borderStyle="round" borderColor={COLOR[row.phase]} paddingX={1}>
        <Text>
          <Text bold>{row.key}</Text>
          <Text color={COLOR[row.phase]} bold>{`  ${LABEL[row.phase]}`}</Text>
          {row.pr && <Text dimColor>{`  #${row.pr}`}</Text>}
        </Text>
        {row.title && <Text>{clip(row.title, width - 6)}</Text>}
        <Box flexDirection="row" flexWrap="wrap">{lamps(row)}</Box>
        <Box flexDirection="column" marginTop={1}>{details(row)}</Box>
        {row.worktree && <Text dimColor>{'↳ ' + clip(row.worktree, width - 8)}</Text>}
        <Box flexDirection="row" gap={1} marginTop={1}>{actionsOf(row)}</Box>
      </Box>
    )

    const doneLine = (row: FlowRow) => (
      <Text>
        <Text color="success">{'✓ '}</Text>
        <Text dimColor>{`${row.key}  ${clip(row.title, width - row.key.length - 14)}`}</Text>
        {row.pr && <Text dimColor>{`  #${row.pr}`}</Text>}
      </Text>
    )

    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text bold>{`◆ ${v.keys.join(' · ')}`}</Text>
          {v.source && <Text dimColor>{`detected from ${v.source}`}</Text>}
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
          const open = group.rows.filter(r => r.phase !== 'merged')
          const done = group.rows.filter(r => r.phase === 'merged')
          return (
            <Box flexDirection="column">
              {group.epicTitle !== undefined && (
                <Box flexDirection="column">
                  <Text>
                    <Text color="claude" bold>{`Epic ${group.key}`}</Text>
                    <Text dimColor>{`  ${clip(group.epicTitle, width - group.key.length - 8)}`}</Text>
                  </Text>
                  <Box flexDirection="row" gap={1}>
                    {action(`${group.key}-epic`, 'Epic status', 'we:epic', group.key)}
                    {open.length > 0 && action(`${group.key}-orchestrate`, 'Orchestrate', 'we:orchestrate', group.key)}
                  </Box>
                </Box>
              )}
              {group.rows.length === 0 && !v.isLoading && <Text dimColor>No story plans on the default branch.</Text>}
              {open.map(openCard)}
              {done.length > 0 && (
                <Box flexDirection="column" marginTop={open.length ? 1 : 0}>
                  {done.map(doneLine)}
                </Box>
              )}
            </Box>
          )
        })}

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
