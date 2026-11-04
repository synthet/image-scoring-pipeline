// @vitest-environment node
/**
 * Contract check between the SPA and the backend (UI E2E suite, #769).
 *
 * - Every HTTP call in src/ (api helper, fetch, URL literals) must exist in openapi.json with
 *   that method.
 * - Every WebSocket message type the SPA handles must be one the backend broadcasts.
 *
 * Known gaps are listed in KNOWN_* with their issue; each has an `it.fails` that starts failing
 * (and must be removed) once the gap is closed.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { extractCalls, matchesTemplate, type ExtractedCall } from './apiContract'

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const REPO = path.resolve(SRC, '../..')

function walk(dir: string, accept: (f: string) => boolean): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name)
    if (statSync(full).isDirectory()) {
      if (name === 'node_modules' || name === '__pycache__' || name === 'test') continue
      out.push(...walk(full, accept))
    } else if (accept(full)) out.push(full)
  }
  return out
}

const spec = JSON.parse(readFileSync(path.join(REPO, 'openapi.json'), 'utf8')) as {
  paths: Record<string, Record<string, unknown>>
}
const documented: { method: string; template: string }[] = Object.entries(spec.paths).flatMap(([template, ops]) =>
  Object.keys(ops)
    .filter((m) => ['get', 'post', 'put', 'patch', 'delete'].includes(m))
    .map((m) => ({ method: m.toUpperCase(), template })),
)

const sources = walk(SRC, (f) => /\.(ts|tsx)$/.test(f) && !/\.(test|spec)\.(ts|tsx)$/.test(f))
const calls: ExtractedCall[] = []
const dynamicCalls: string[] = []
for (const file of sources) {
  const rel = path.relative(SRC, file).replace(/\\/g, '/')
  const { calls: found, dynamic } = extractCalls(rel, readFileSync(file, 'utf8'))
  calls.push(...found)
  dynamicCalls.push(...dynamic)
}

const key = (c: { method: string; path: string }) => `${c.method} ${c.path}`
const undocumented = [...new Set(calls.filter((c) => !documented.some((d) => d.method === c.method && matchesTemplate(c.path, d.template))).map(key))].sort()

/** Calls the SPA makes that openapi.json does not document, by issue. */
const KNOWN_UNDOCUMENTED: Record<string, string> = {
  'POST /api/db/query': '#770',
  'GET /api/status/log-tails': '#770',
}

describe('HTTP contract: SPA calls vs openapi.json', () => {
  it('finds the SPA calls (extractor sanity)', () => {
    expect(calls.length).toBeGreaterThan(50)
    expect(calls.map(key)).toContain('GET /api/jobs/recent')
    expect(calls.map(key)).toContain('GET /api/images/{}')
  })

  it('every call is documented, apart from the known gaps', () => {
    expect(undocumented.filter((k) => !(k in KNOWN_UNDOCUMENTED))).toEqual([])
  })

  for (const [call, issue] of Object.entries(KNOWN_UNDOCUMENTED)) {
    it.fails(`known gap ${issue}: ${call} is documented`, () => {
      expect(undocumented).not.toContain(call)
    })
  }

  it('every helper call uses a literal path the check can read', () => {
    expect(dynamicCalls).toEqual([])
  })
})

// ─── WebSocket ───────────────────────────────────────────────────────────

const adapter = readFileSync(path.join(SRC, 'utils/adaptBackendMessage.ts'), 'utf8')
const bumpSet = /const BUMP_STATUSES = new Set\(\[([\s\S]*?)\]\)/.exec(adapter)?.[1] ?? ''
const handledTypes = [
  ...new Set([
    ...[...adapter.matchAll(/type === '([a-z_]+)'/g)].map((m) => m[1]),
    ...[...bumpSet.matchAll(/'([a-z_]+)'/g)].map((m) => m[1]),
  ]),
].sort()

const python = walk(path.join(REPO, 'modules'), (f) => f.endsWith('.py'))
const emitted = new Set<string>()
const jobStatuses = new Set<string>()
let dynamicJobEvents = false
let variableJobStatus = false
for (const file of python) {
  const text = readFileSync(file, 'utf8')
  for (const m of text.matchAll(/\b(?:broadcast|broadcast_threadsafe|_broadcast_drive)\(\s*["']([a-z_]+)["']/g)) emitted.add(m[1])
  if (/def broadcast_run_log_line/.test(text) && /["']log_line["']/.test(text)) emitted.add('log_line')
  // db_operations/job_lifecycle.py broadcasts f"job_{status}" on every update_job_status().
  if (/broadcast_threadsafe\(\s*f["']job_\{/.test(text)) dynamicJobEvents = true
  for (const m of text.matchAll(/\bupdate_job_status\(\s*[^,()]+,\s*["']([a-z_]+)["']/g)) jobStatuses.add(m[1])
  if (/\bupdate_job_status\(\s*[^,()]+,\s*[a-z_]+\s*[,)]/.test(text)) variableJobStatus = true
}
if (dynamicJobEvents) for (const s of jobStatuses) emitted.add(`job_${s}`)
/**
 * job_<status> types not proven by a literal status. When some update_job_status() call passes a
 * variable status (api/deps.py, api_db.py), they may still be emitted, so they are reported, not
 * failed. Only the Tier 2 live smoke can observe them.
 */
const unverifiable = handledTypes.filter(
  (t) => !emitted.has(t) && dynamicJobEvents && variableJobStatus && t.startsWith('job_'),
)
const neverEmitted = handledTypes.filter((t) => !emitted.has(t) && !unverifiable.includes(t))

/** Message types the SPA handles that no backend code broadcasts, by issue. */
const KNOWN_NOT_EMITTED: Record<string, string> = {
  run_progress: '#772',
  stage_transition: '#772',
  queue_update: '#772',
  work_item_done: '#772',
}

describe('WebSocket contract: SPA handlers vs backend broadcasts', () => {
  it('finds handled and emitted types (extractor sanity)', () => {
    expect(handledTypes).toContain('job_progress')
    expect(emitted.has('job_completed')).toBe(true)
    expect(dynamicJobEvents).toBe(true)
    // Listed for the catalog; not a failure (see `unverifiable`).
    console.info(`[contract] job_* types not provable statically: ${unverifiable.join(', ') || 'none'}`)
  })

  it('every handled type is broadcast by the backend, apart from the known gaps', () => {
    expect(neverEmitted.filter((t) => !(t in KNOWN_NOT_EMITTED))).toEqual([])
  })

  for (const [type, issue] of Object.entries(KNOWN_NOT_EMITTED)) {
    it.fails(`known gap ${issue}: '${type}' is broadcast by the backend`, () => {
      expect(neverEmitted).not.toContain(type)
    })
  }
})
