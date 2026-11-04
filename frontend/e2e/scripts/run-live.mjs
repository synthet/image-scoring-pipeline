#!/usr/bin/env node
/**
 * UI E2E Tier 2 (live stack): real webui.py + FastAPI + SPA against image_scoring_test.
 *
 *   npm run e2e:live            (needs Docker with `db` running; builds nothing)
 *
 * Isolation from the developer's instance:
 * - A one-off `docker compose run` container of the gpu-shell service, on a free host port (never
 *   7860). Running containers are not touched, and `--no-deps` starts nothing else.
 * - POSTGRES_DB=image_scoring_test; seed_live_db.py refuses any other database.
 * - WEBUI_LOCK_FILE points inside the container, so the repo-root webui.lock is not written or
 *   deleted. webui.log (always the repo root, see webui.py) is bind-mounted to a temp file.
 * - Every repo-root file is fingerprinted before and after; any change fails the run.
 */
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdtempSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const REPO = path.resolve(FRONTEND, '..')
const PLAYWRIGHT = path.join(FRONTEND, 'node_modules/@playwright/test/cli.js')
const STARTUP_TIMEOUT_MS = 240_000

function freePort() {
  return new Promise((resolve, reject) => {
    const s = net.createServer()
    s.on('error', reject)
    s.listen(0, '127.0.0.1', () => {
      const { port } = s.address()
      s.close(() => (port === 7860 ? resolve(freePort()) : resolve(port)))
    })
  })
}

/** name → size:mtime:sha of every file directly in the repo root. */
function rootFingerprint() {
  const out = {}
  for (const name of readdirSync(REPO)) {
    const full = path.join(REPO, name)
    const st = statSync(full, { throwIfNoEntry: false })
    if (!st?.isFile()) continue
    const sha = st.size < 1_000_000 ? createHash('sha1').update(readFileSync(full)).digest('hex') : ''
    out[name] = `${st.size}:${st.mtimeMs}:${sha}`
  }
  return out
}

function docker(args) {
  return spawnSync('docker', args, { cwd: REPO, encoding: 'utf8' })
}

async function waitForHealth(url, container) {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`${url}/api/health`, { signal: AbortSignal.timeout(3000) })
      if (r.ok) return
    } catch {
      /* not up yet */
    }
    if (docker(['inspect', '-f', '{{.State.Running}}', container]).stdout.trim() !== 'true') {
      throw new Error(`container ${container} exited during startup`)
    }
    await new Promise((r) => setTimeout(r, 2000))
  }
  throw new Error(`no healthy WebUI at ${url} after ${STARTUP_TIMEOUT_MS / 1000} s`)
}

const port = await freePort()
const url = `http://127.0.0.1:${port}`
const container = `ui-e2e-live-${port}`
const tmp = mkdtempSync(path.join(os.tmpdir(), 'ui-e2e-live-'))
const logFile = path.join(tmp, 'webui.log')
writeFileSync(logFile, '')
const before = rootFingerprint()

const started = docker([
  // The service's entrypoint is `sleep`, so the command needs its own entrypoint.
  'compose', '--profile', 'gpu-shell', 'run', '-d', '--no-deps', '--entrypoint', 'bash', '--name', container,
  '-p', `127.0.0.1:${port}:${port}`,
  '-e', 'WEBUI_HOST=0.0.0.0',
  '-e', `WEBUI_PORT=${port}`,
  '-e', 'POSTGRES_DB=image_scoring_test',
  '-e', 'WEBUI_LOCK_FILE=/tmp/ui-e2e-webui.lock',
  '-e', 'PYTHONPATH=/app',
  '-v', `${logFile.replace(/\\/g, '/')}:/app/webui.log`,
  'gpu-shell',
  '-lc', 'cd /app && python frontend/e2e/live/seed_live_db.py && exec python webui.py',
])
if (started.status !== 0) {
  console.error(`could not start ${container}:\n${started.stderr}`)
  process.exit(1)
}

let status = 1
try {
  console.log(`live tier: ${container} on ${url} (test database); waiting for /api/health`)
  await waitForHealth(url, container)
  const t = spawnSync(process.execPath, [PLAYWRIGHT, 'test', '-c', 'e2e/playwright.config.ts', ...process.argv.slice(2)], {
    cwd: FRONTEND,
    stdio: 'inherit',
    env: { ...process.env, UI_E2E_LIVE: '1', UI_E2E_LIVE_URL: url },
  })
  status = t.status ?? 1
} catch (err) {
  console.error(String(err))
  const logs = docker(['logs', '--tail', '30', container])
  console.error(logs.stdout + logs.stderr)
} finally {
  docker(['stop', '-t', '10', container])
  docker(['rm', container])
}

const after = rootFingerprint()
const changed = [...new Set([...Object.keys(before), ...Object.keys(after)])].filter((k) => before[k] !== after[k])
if (changed.length) {
  console.error(`live tier changed repo-root files: ${changed.join(', ')}`)
  status = status || 1
} else {
  console.log('repo-root files unchanged (webui.lock, webui.log, config included)')
}
process.exit(status)
