/**
 * Journey 10 — long operations. A run reports progress over the WebSocket, can be cancelled
 * (POST /api/runs/{id}/cancel), and must end in a consistent state after completion, failure or
 * cancel. Lists poll every 30 s and Run detail treats its 30 s refetch as a watchdog only, so
 * every final state below arrives inside LIVE_MS through WebSocket invalidation.
 * Exports and uploads: the SPA has none.
 */
import { test, expect, type ApiFake, type WsFake } from '../fixtures'
import { installPages, iso, run, runsBackend, stage } from '../builders'
import type { Run, Stage } from '../../src/types/api'

const LIVE_MS = 8_000

function progress(ws: WsFake, current: number, total = 100) {
  ws.send({ type: 'job_progress', data: { job_id: 3, job_type: 'scoring', current, total } })
}

function finish(runs: Run[], ws: WsFake, status: 'completed' | 'failed', error?: string) {
  Object.assign(runs[0], { status, finished_at: iso(9999), current_phase: null, log: error ?? null })
  ws.send({
    type: `job_${status}`,
    data: { job_id: 3, status, current_phase: null, next_phase_index: null, runner_state: status, ...(error ? { error } : {}) },
  })
}

function running(api: ApiFake): Run[] {
  const runs = runsBackend(api, [run(3, { status: 'running', finished_at: null, current_phase: 'scoring' })])
  installPages(api)
  // job_phases follow the run: the scoring stage is running until the run ends, then takes the
  // run's terminal state (as the backend's terminal reconcile does).
  api.on('GET', '/api/runs/{run_id}/stages', () => {
    const s = runs[0].status
    const scoringState = s === 'running' ? 'running' : s === 'canceled' ? 'canceled' : s
    return {
      json: [
        stage(1, 'indexing'),
        stage(2, 'metadata'),
        stage(3, 'scoring', { state: scoringState as Stage['state'], completed_at: s === 'running' ? null : iso(9999) }),
      ],
    }
  })
  return runs
}

test('live progress climbs to the end and the run settles as Completed in the list and in History', async ({ page, api, ws }) => {
  const runs = running(api)
  await page.goto('/ui/runs')
  await expect(page.getByText('#3', { exact: true })).toBeVisible()
  await ws.waitForOpen()
  for (const pct of [25, 50, 75]) {
    progress(ws, pct)
    await expect(page.getByText(`${pct}%`)).toBeVisible({ timeout: LIVE_MS })
  }
  progress(ws, 100)
  finish(runs, ws, 'completed')
  await expect(page.getByText('#3', { exact: true })).toHaveCount(0, { timeout: LIVE_MS })
  await page.getByRole('button', { name: /History/ }).click()
  await expect(page.getByText('#3', { exact: true })).toBeVisible()
  await expect(page.getByText('Completed', { exact: true }).first()).toBeVisible()
  await expect(page.getByText(/\d+%/)).toHaveCount(0)
})

test('a run that fails mid-way shows Failed with its error and offers Retry', async ({ page, api, ws }) => {
  const runs = running(api)
  await page.goto('/ui/runs/3')
  await expect(page.getByRole('heading', { level: 1, name: 'Run #3' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cancel', exact: true })).toBeVisible()
  await ws.waitForOpen()
  progress(ws, 40)
  finish(runs, ws, 'failed', 'scoring failed: model not loaded')

  await expect(page.getByText('Failed', { exact: true }).first()).toBeVisible({ timeout: LIVE_MS })
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cancel', exact: true })).toHaveCount(0)
  await expect(page.getByText('scoring failed: model not loaded').first()).toBeVisible()
})

test('a run cancelled during progress stays Canceled when a late progress event arrives', async ({ page, api, ws }) => {
  const runs = running(api)
  api.on('POST', '/api/runs/{run_id}/cancel', () => {
    Object.assign(runs[0], { status: 'canceled', finished_at: iso(9999), current_phase: null })
    ws.send({ type: 'job_cancelled', data: { job_id: 3, status: 'cancelled', current_phase: null, next_phase_index: null, runner_state: 'cancelled' } })
    return { json: { success: true, message: 'Run 3 canceled', method: 'update_status' } }
  })
  await page.goto('/ui/runs/3')
  await expect(page.getByRole('heading', { level: 1, name: 'Run #3' })).toBeVisible()
  await ws.waitForOpen()
  progress(ws, 30)
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(page.getByText('Canceled', { exact: true }).first()).toBeVisible({ timeout: LIVE_MS })
  await expect(page.getByText('Running', { exact: true })).toHaveCount(0, { timeout: LIVE_MS })

  // A worker that was mid-image can still emit one more progress event after the cancel.
  progress(ws, 35)
  await page.waitForTimeout(1500)
  await expect(page.getByText('Canceled', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Running', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Cancel', exact: true })).toHaveCount(0)
  expect(api.calls('POST', '/api/runs/{run_id}/cancel')).toHaveLength(1)
})
