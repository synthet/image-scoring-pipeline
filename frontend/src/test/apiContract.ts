/**
 * Static extraction of the HTTP calls the SPA makes, for the contract test (contract.test.ts).
 *
 * Three call shapes exist in src/:
 *  1. the `api.get|post|put|patch|delete(path, …)` helper (src/api/client.ts, BASE = '/api');
 *  2. direct `fetch('/api/…', { method })`;
 *  3. URL literals handed to <img>/links (`/source-image?path=…`, `/api/images/${id}/evidence/…`).
 * Template expressions `${…}` become a placeholder; a placeholder that fills a whole path
 * segment is a path parameter, one glued to a literal segment is a query-string suffix.
 */
export interface ExtractedCall {
  method: string
  /** Normalized path, parameters as `{}`; includes the /api prefix. */
  path: string
  file: string
  line: number
  raw: string
}

const HOLE = '\u0000'

/** Read a string/template literal starting at text[i]; returns [content with holes, end index]. */
export function readLiteral(text: string, i: number): [string, number] | null {
  const quote = text[i]
  if (quote !== "'" && quote !== '"' && quote !== '`') return null
  let out = ''
  let j = i + 1
  while (j < text.length) {
    const c = text[j]
    if (c === '\\') {
      out += text[j + 1] ?? ''
      j += 2
      continue
    }
    if (c === quote) return [out, j + 1]
    if (quote === '`' && c === '$' && text[j + 1] === '{') {
      j = skipExpression(text, j + 2)
      out += HOLE
      continue
    }
    out += c
    j += 1
  }
  return null
}

/** Skip a `${ … }` expression body (nested braces and template literals), return index after `}`. */
function skipExpression(text: string, j: number): number {
  let depth = 1
  while (j < text.length && depth > 0) {
    const c = text[j]
    if (c === '`' || c === "'" || c === '"') {
      const lit = readLiteral(text, j)
      j = lit ? lit[1] : j + 1
      continue
    }
    if (c === '{') depth += 1
    else if (c === '}') depth -= 1
    j += 1
  }
  return j
}

/** Skip a balanced generic argument list `<…>` starting at text[i] === '<'. */
function skipGeneric(text: string, i: number): number {
  let depth = 0
  let j = i
  while (j < text.length) {
    const c = text[j]
    if (c === '<') depth += 1
    else if (c === '>' && text[j - 1] !== '=') {
      depth -= 1
      if (depth === 0) return j + 1
    }
    j += 1
  }
  return j
}

export function normalizePath(raw: string, prefix = ''): string {
  const pathPart = raw.split('?')[0]
  const segments = (prefix + pathPart).split('/').map((seg) => {
    if (seg === HOLE) return '{}'
    return seg.split(HOLE)[0] // a hole glued to a literal is a query/suffix expression
  })
  let path = segments.join('/')
  if (path.length > 1) path = path.replace(/\/+$/, '')
  return path
}

const lineOf = (text: string, index: number) => text.slice(0, index).split('\n').length

export function extractCalls(file: string, text: string): { calls: ExtractedCall[]; dynamic: string[] } {
  const calls: ExtractedCall[] = []
  const dynamic: string[] = []
  const seen = new Set<number>()

  // 1. api.<method>(literal …)
  for (const m of text.matchAll(/\bapi\.(get|post|put|patch|delete)\b/g)) {
    let j = m.index! + m[0].length
    while (/\s/.test(text[j])) j++
    if (text[j] === '<') j = skipGeneric(text, j)
    while (/\s/.test(text[j])) j++
    if (text[j] !== '(') continue
    j++
    while (/\s/.test(text[j])) j++
    const lit = readLiteral(text, j)
    if (!lit) {
      dynamic.push(`${file}:${lineOf(text, m.index!)} api.${m[1]}(<non-literal path>)`)
      continue
    }
    seen.add(j)
    calls.push({ method: m[1].toUpperCase(), path: normalizePath(lit[0], '/api'), file, line: lineOf(text, j), raw: lit[0] })
  }

  // 2. fetch(literal, { method: '…' })
  for (const m of text.matchAll(/\bfetch\(\s*/g)) {
    const j = m.index! + m[0].length
    const lit = readLiteral(text, j)
    if (!lit) continue
    seen.add(j)
    const tail = text.slice(lit[1], lit[1] + 200)
    const close = tail.indexOf(')')
    const method = /method:\s*['"](\w+)['"]/.exec(close >= 0 ? tail.slice(0, close) : tail)?.[1] ?? 'GET'
    if (!/^\/(api|public\/api|source-image)\b/.test(lit[0])) continue
    calls.push({ method: method.toUpperCase(), path: normalizePath(lit[0]), file, line: lineOf(text, j), raw: lit[0] })
  }

  // 3. bare URL literals used as src/href
  // (a following / or ? excludes the bare BASE constant '/api' in client.ts)
  for (const m of text.matchAll(/['"`]\/(api|public\/api|source-image)(?=[/?])/g)) {
    if (seen.has(m.index!)) continue
    const lit = readLiteral(text, m.index!)
    if (!lit) continue
    calls.push({ method: 'GET', path: normalizePath(lit[0]), file, line: lineOf(text, m.index!), raw: lit[0] })
  }
  return { calls, dynamic }
}

/** Segment-wise match: `{}` must align with a template parameter; literals must be equal. */
export function matchesTemplate(path: string, template: string): boolean {
  const a = path.split('/')
  const b = template.split('/')
  if (a.length !== b.length) return false
  return a.every((seg, i) => {
    const t = b[i]
    const tParam = t.startsWith('{') && t.endsWith('}')
    if (seg === '{}') return tParam
    return tParam || seg === t
  })
}
