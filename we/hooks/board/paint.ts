// A plain-text drawing of a pane's tree, for the render tests: Box (column, row, round border, padding,
// margin, gap), Text and Button as the terminal lays them out, every glyph one column wide.
type Node = string | number | boolean | null | undefined | { type: string; props?: Record<string, unknown>; children?: Node[] }

const num = (v: unknown) => (typeof v === 'number' ? v : 0)

const textOf = (n: Node): string => {
  if (n === null || n === undefined || typeof n === 'boolean') return ''
  if (typeof n !== 'object') return String(n)
  if (n.type === 'Button') return `[ ${String(n.props?.label ?? '')} ]`
  return (n.children ?? []).map(textOf).join('')
}

// Word wrap as Ink does it: break at spaces, a word longer than the line is cut.
const wrap = (text: string, width: number): string[] => {
  const out: string[] = []
  for (const para of text.split('\n')) {
    let line = ''
    for (const word of para.split(' ')) {
      const next = line ? `${line} ${word}` : word
      if (next.length <= width) {
        line = next
        continue
      }
      if (line) out.push(line)
      line = word
      while (line.length > width) {
        out.push(line.slice(0, width))
        line = line.slice(width)
      }
    }
    out.push(line)
  }
  return out
}

export const paint = (n: Node, width: number): string[] => {
  if (n === null || n === undefined || typeof n === 'boolean') return []
  if (typeof n !== 'object' || n.type !== 'Box') return wrap(textOf(n), width)
  const p = n.props ?? {}
  const border = p.borderStyle ? 1 : 0
  const padX = num(p.paddingX)
  const padL = num(p.paddingLeft) + padX
  const inner = width - 2 * border - padL - padX
  const kids = (n.children ?? []).filter(k => k !== null && k !== undefined && typeof k !== 'boolean')
  const gap = num(p.gap)
  let body: string[]
  if (p.flexDirection === 'row') {
    body = [kids.map(k => paint(k, inner)[0] ?? '').join(' '.repeat(gap))]
  } else {
    body = kids.flatMap((k, i) => [...(i && gap ? Array(gap).fill('') : []), ...paint(k, inner)])
  }
  body = body.map(line => ' '.repeat(padL) + line)
  if (border) {
    body = [
      `╭${'─'.repeat(width - 2)}╮`,
      ...body.map(line => `│${line.padEnd(width - 2 - padX)}${' '.repeat(padX)}│`),
      `╰${'─'.repeat(width - 2)}╯`,
    ]
  }
  return [...Array(num(p.marginTop)).fill(''), ...body]
}
