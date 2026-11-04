/**
 * Journey 3 — runs, the core flow. WebSocket messages use the backend's shapes:
 * modules/events.py wraps every event as {type, data}; job_progress data is
 * {job_id, job_type, current, total}; job_<status> comes from update_job_status
 * (the DB spelling "cancelled" is broadcast as job_cancelled, REST normalizes it to "canceled").
 *
 * The active runs list polls every 30 s (RunsPage.tsx), so the live tests wait at most
 * LIVE_MS — an update inside that window can only have come from the WebSocket.
 */
import { test, expect } from '../fixtures'
import { defaultRuns, installPages, iso, run, runsBackend } from '../builders'

const LIVE_MS = 8_000

test('runs list shows the running run under Active and finished runs under History with their status', async ({ page, api }) => {
  installPages(api)
  await page.goto('/ui/runs')
  await expect(page.getByText('#3', { exact: true })).toBeVisible()
  await expect(page.getByText('Running', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('#2', { exact: true })).toHaveCount(0)

  await page.getByRole('button', { name: /History/ }).click()
  await expect(page.getByText('#2', { exact: true })).toBeVisible()
  await expect(page.getByText('#1', { exact: true })).toBeVisible()
  await expect(page.getByText('Completed', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Failed', { exact: true }).first()).toBeVisible()
  expect(api.calls('GET', '/api/jobs/recent').some((c) => c.path.includes('history=true'))).toBe(true)
})

test('progress pushed over the WebSocket appears on the active run card', async ({ page, api, ws }) => {
  installPages(api)
  await page.goto('/ui/runs')
  await expect(page.getByText('#3', { exact: true })).toBeVisible()
  await ws.waitForOpen()

  ws.send({ type: 'job_progress', data: { job_id: 3, job_type: 'scoring', current: 40, total: 100 } })
  await expect(page.getByText('40%')).toBeVisible({ timeout: LIVE_MS })
})

test('a status change pushed live moves the run off Active without a reload', async ({ page, api, ws }) => {
  const runs = runsBackend(api, defaultRuns())
  installPages(api)
  await page.goto('/ui/runs')
  await expect(page.getByText('#3', { exact: true })).toBeVisible()
  await ws.waitForOpen()
  const before = api.calls('GET', '/api/jobs/recent').length

  Object.assign(runs[0], { status: 'completed', finished_at: iso(9999), current_phase: null })
  ws.send({ type: 'job_completed', data: { job_id: 3, status: 'completed', current_phase: null, next_phase_index: null, runner_state: 'completed' } })

  await expect(page.getByText('#3', { exact: true })).toHaveCount(0, { timeout: LIVE_MS })
  expect(api.calls('GET', '/api/jobs/recent').length).toBeGreaterThan(before)
})

test('run detail shows the run, its stages, and live log lines in the order they arrive', async ({ page, api, ws }) => {
  installPages(api)
  await page.goto('/ui/runs/3')
  await expect(page.getByRole('heading', { level: 1, name: 'Run #3' })).toBeVisible()
  await expect(page.getByText('Run Log')).toBeVisible()
  await ws.waitForOpen()

  const lines = ['line one: indexing 120 files', 'line two: metadata done', 'line three: scoring 40/120']
  for (const message of lines) {
    ws.send({ type: 'log_line', data: { run_id: 3, level: 'INFO', message, ts: iso(100) } })
  }
  for (const message of lines) await expect(page.getByText(message)).toBeVisible({ timeout: LIVE_MS })

  const body = await page.locator('body').innerText()
  const positions = lines.map((l) => body.indexOf(l))
  expect(positions).toEqual([...positions].sort((a, b) => a - b))

  // A line for another run must not show up here.
  ws.send({ type: 'log_line', data: { run_id: 2, level: 'INFO', message: 'belongs to run 2', ts: iso(101) } })
  ws.send({ type: 'log_line', data: { run_id: 3, level: 'INFO', message: 'line four: marker', ts: iso(102) } })
  await expect(page.getByText('line four: marker')).toBeVisible({ timeout: LIVE_MS })
  await expect(page.getByText('belongs to run 2')).toHaveCount(0)
})

test('cancelling a running run sends POST /api/runs/{id}/cancel and the page shows Canceled', async ({ page, api, ws }) => {
  const runs = runsBackend(api, [run(3, { status: 'running', finished_at: null, current_phase: 'scoring' })])
  installPages(api)
  // electron_runs_lifecycle.cancel_run: update_job_status(run_id, "cancelled"), then
  // {"success": True, "message": ...}; the next GET returns status "canceled" (api_helpers.py).
  api.on('POST', '/api/runs/{run_id}/cancel', ({ params }) => {
    const target = runs.find((r) => r.id === Number(params.run_id))!
    Object.assign(target, { status: 'canceled', finished_at: iso(9999), current_phase: null })
    ws.send({ type: 'job_cancelled', data: { job_id: target.id, status: 'cancelled', current_phase: null, next_phase_index: null, runner_state: 'cancelled' } })
    return { json: { success: true, message: `Run ${target.id} canceled`, method: 'update_status' } }
  })

  await page.goto('/ui/runs/3')
  await expect(page.getByRole('heading', { level: 1, name: 'Run #3' })).toBeVisible()
  await ws.waitForOpen()
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()

  await expect.poll(() => api.calls('POST', '/api/runs/{run_id}/cancel').map((c) => c.path)).toEqual(['/api/runs/3/cancel'])
  await expect(page.getByText('Canceled', { exact: true }).first()).toBeVisible({ timeout: LIVE_MS })
  await expect(page.getByRole('button', { name: 'Cancel', exact: true })).toHaveCount(0)
})
