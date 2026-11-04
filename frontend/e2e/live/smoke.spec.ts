/**
 * Tier 2 smoke journeys through the real FastAPI app and the SPA mount (see scripts/run-live.mjs).
 * Runs against the committed SPA build in static/app and the seeded test database.
 */
import { expect, test } from '@playwright/test'

test('/ redirects to the SPA and lands on the runs list', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/ui\/runs$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Runs' })).toBeVisible()
})

test('deep links load through the SPA fallback and survive a reload', async ({ page }) => {
  await page.goto('/ui/diagnostics')
  await expect(page.getByRole('heading', { name: 'Health' }).first()).toBeVisible()
  await page.reload()
  await expect(page).toHaveURL(/\/ui\/diagnostics$/)
  await expect(page.getByRole('heading', { name: 'Health' }).first()).toBeVisible()
})

test('the runs list shows the seeded run from the real API', async ({ page }) => {
  await page.goto('/ui/runs')
  await page.getByRole('button', { name: /History/ }).click()
  await expect(page.getByText('ui-e2e-live-seed').first()).toBeVisible()
})

test('the live-updates WebSocket connects', async ({ page }) => {
  await page.goto('/ui/runs')
  await expect(page.getByText('Live', { exact: true })).toBeVisible({ timeout: 15_000 })
})

test('the real API answers the shapes the fixtures assume', async ({ request }) => {
  const recent = await (await request.get('/api/jobs/recent?limit=5')).json()
  expect(Array.isArray(recent.runs), '/api/jobs/recent returns {runs, jobs}').toBe(true)
  expect(Array.isArray(recent.jobs)).toBe(true)
  const history = await (await request.get('/api/jobs/recent?limit=5&history=true')).json()
  expect(typeof history.total).toBe('number')

  const tree = await (await request.get('/api/folders/tree')).json()
  expect(Array.isArray(tree.tree), '/api/folders/tree returns {tree, count}').toBe(true)

  const drive = await (await request.get('/api/runs/drive/status')).json()
  expect(drive).toHaveProperty('state')
  expect(drive).toHaveProperty('outstanding')
})
