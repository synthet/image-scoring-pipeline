#!/usr/bin/env node
/**
 * Fail-path proofs for the UI E2E suite.
 *
 * For each break below: apply it to the product source, rebuild the e2e bundle, run the test
 * that covers that path and require it to FAIL; then restore the file. Afterwards the tracked
 * tree under frontend/src must be unchanged (git diff --exit-code).
 *
 *   npm run e2e:prove                 all breaks
 *   npm run e2e:prove -- smoke-root   only the named break(s)
 *
 * A break must match its `find` text exactly once, so a refactor that moves the code makes the
 * proof fail loudly instead of silently testing nothing.
 */
import { execFileSync, spawnSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const isWin = process.platform === 'win32'
const npx = isWin ? 'npx.cmd' : 'npx'

/**
 * runner 'playwright' (default): rebuild the e2e bundle, run tests matching `grep`.
 * runner 'vitest': run `vitestFile` with `-t grep` (no rebuild).
 * @type {{ name: string, file: string, find: string, replace: string, grep: string, runner?: 'playwright'|'vitest', vitestFile?: string }[]}
 */
export const BREAKS = [
  {
    name: 'smoke-root',
    file: 'src/App.tsx',
    find: '<Route index element={<Navigate to="/runs" replace />} />',
    replace: '<Route index element={<Navigate to="/dashboard" replace />} />',
    grep: 'opening /ui/ lands on the runs list',
  },
  {
    name: 'contract-undocumented-call',
    file: 'src/api/runs.ts',
    find: 'get: (id: number) => api.get<Run>(`/jobs/${id}`),',
    replace: 'get: (id: number) => api.get<Run>(`/jobz/${id}`),',
    grep: 'every call is documented',
    runner: 'vitest',
    vitestFile: 'src/test/contract.test.ts',
  },
  {
    name: 'ws-no-reconnect',
    file: 'src/hooks/useWebSocket.ts',
    find: 'reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)',
    replace: 'reconnectTimer.current = null',
    grep: 'reconnects after a live socket closes',
    runner: 'vitest',
    vitestFile: 'src/hooks/useWebSocket.test.tsx',
  },
]

function run(cmd, args, opts = {}) {
  return spawnSync(cmd, args, { cwd: FRONTEND, stdio: 'pipe', encoding: 'utf8', shell: isWin, ...opts })
}

function build() {
  const r = run(npx, ['vite', 'build', '--config', 'e2e/vite.e2e.config.ts'])
  if (r.status !== 0) throw new Error(`e2e build failed:\n${r.stdout}\n${r.stderr}`)
}

function gitClean() {
  execFileSync('git', ['diff', '--exit-code', '--quiet', '--', 'src'], { cwd: FRONTEND })
}

const wanted = process.argv.slice(2)
const selected = wanted.length ? BREAKS.filter((b) => wanted.includes(b.name)) : BREAKS
if (wanted.length && selected.length !== wanted.length) {
  console.error(`unknown break(s): ${wanted.filter((w) => !BREAKS.some((b) => b.name === w)).join(', ')}`)
  process.exit(2)
}

gitClean()
const results = []
for (const brk of selected) {
  const file = path.join(FRONTEND, brk.file)
  const original = readFileSync(file, 'utf8')
  const count = original.split(brk.find).length - 1
  if (count !== 1) {
    results.push({ name: brk.name, ok: false, why: `find text matched ${count} times in ${brk.file}` })
    continue
  }
  try {
    writeFileSync(file, original.replace(brk.find, brk.replace))
    let t
    let ran
    if (brk.runner === 'vitest') {
      t = run(npx, ['vitest', 'run', brk.vitestFile, '-t', brk.grep])
      ran = /Tests\s+.*\d+ (passed|failed)/.test(t.stdout.replace(/\x1b\[[0-9;]*m/g, ''))
    } else {
      build()
      t = run(npx, ['playwright', 'test', '-c', 'e2e/playwright.config.ts', '-g', brk.grep, '--reporter=line'])
      ran = /\d+ (passed|failed)/.test(t.stdout)
    }
    results.push({
      name: brk.name,
      ok: ran && t.status !== 0,
      why: !ran ? 'no test matched the grep' : t.status !== 0 ? 'test failed as required' : 'TEST STILL PASSED',
    })
  } finally {
    writeFileSync(file, original)
  }
}
if (selected.some((b) => b.runner !== 'vitest')) build() // leave a bundle built from the real source
gitClean()

for (const r of results) console.log(`${r.ok ? 'PROVEN ' : 'NOT PROVEN'}  ${r.name}: ${r.why}`)
process.exit(results.every((r) => r.ok) ? 0 : 1)
