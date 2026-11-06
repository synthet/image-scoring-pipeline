/**
 * Journey 4 — backend unavailable: REST failing or hanging, the live-updates WebSocket refused
 * or dropped, and recovery when the backend returns.
 */
import type { Page } from '@playwright/test'
import { test, expect, type AllowedError } from '../fixtures'
import { installPages } from '../builders'

const LABEL = /^(Live|Connecting…|Reconnecting…|Offline)$/
const resourceErrors: AllowedError = {
  pattern: /Failed to load resource: the server responded with a status of 50\d/,
  reason: 'the browser logs every failed request while the backend is down',
}
const missingResource: AllowedError = {
  pattern: /Failed to load resource: the server responded with a status of 404/,
  reason: 'the browser logs a 404 for the run or folder that does not exist',
}
const refusedSocket: AllowedError = {
  pattern: /WebSocket connection to 'ws:\/\/127\.0\.0\.1:9\/ws\/updates' failed/,
  reason: 'the browser logs each refused handshake (the fake points refused sockets at a closed port)',
}

const loadError = (page: Page) => page.getByRole('alert').filter({ hasText: 'Could not load' })

const MAIN_ROUTES = ['/ui/runs', '/ui/runs/3', '/ui/dashboard', '/ui/images', '/ui/images/1', '/ui/folder/1', '/ui/stacks/1',
  '/ui/birds', '/ui/keywords/bird', '/ui/diagnostics', '/ui/logs', '/ui/db']

test('with /api answering 500, no page is blank and none throws', async ({ page, api, allowErrors }) => {
  allowErrors.push(resourceErrors)
  api.outage = { status: 500 }
  for (const route of MAIN_ROUTES) {
    await page.goto(route)
    // Wait until the page settles on something (error, empty state, or data) — never blank.
    await expect.poll(async () => (await page.locator('main').innerText()).trim().length, { message: `${route} main text` }).toBeGreaterThan(10)
  }
})

test('a 500 is reported as an error, not as "not found" or as no data', async ({ page, api, allowErrors }) => {
  allowErrors.push(resourceErrors)
  api.outage = { status: 500 }
  const misleading: [string, RegExp][] = [
    ['/ui/runs', /No active runs/],
    ['/ui/runs/3', /Run #3 not found/],
    ['/ui/folder/1', /Folder #1 not found/],
    ['/ui/images', /No images in this scope/],
    ['/ui/stacks/1', /^0 images/],
    ['/ui/keywords/bird', /No images for this keyword/],
  ]
  for (const [route, text] of misleading) {
    await page.goto(route)
    // Queries retry once, so wait for the error itself: a page still loading shows neither text.
    await expect(loadError(page).first(), `${route} must report the failure`).toBeVisible()
    await expect(page.getByRole('button', { name: 'Retry' }).first()).toBeVisible()
    await expect.soft(page.getByText(text), `${route} must not claim "${text.source}" when the backend fails`).toHaveCount(0)
  }
})

test('a real 404 still says "not found"', async ({ page, api, allowErrors }) => {
  allowErrors.push(missingResource)
  api.outage = { status: 404 }
  for (const [route, text] of [['/ui/runs/3', 'Run #3 not found'], ['/ui/folder/1', 'Folder #1 not found']]) {
    await page.goto(route)
    await expect(page.getByText(text)).toBeVisible()
    await expect(loadError(page)).toHaveCount(0)
  }
})

test('a failed page recovers through Retry when the backend comes back', async ({ page, api, allowErrors }) => {
  allowErrors.push(resourceErrors)
  installPages(api)
  api.outage = { status: 500 }
  await page.goto('/ui/images')
  await expect(loadError(page)).toBeVisible()
  api.outage = null
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(loadError(page)).toHaveCount(0)
  await expect(page.getByRole('table')).toBeVisible()
})

test('requests that hang leave the shell and a loading state, not a blank page or a verdict', async ({ page, api }) => {
  api.outage = { status: 500, delayMs: 8_000 } // longer than the 2 s the test watches
  await page.goto('/ui/runs/3')
  await expect(page.getByRole('navigation').getByRole('link', { name: 'Runs' })).toBeVisible()
  await page.waitForTimeout(2000)
  await expect(page.getByRole('status', { name: 'Loading' })).toBeVisible()
  await expect(page.getByText('Run #3 not found')).toHaveCount(0)
  await expect(page.getByRole('heading', { level: 1, name: 'Run #3' })).toHaveCount(0)
  api.outage = null
})

test('Diagnostics and Logs recover through Retry when the backend comes back', async ({ page, api, allowErrors }) => {
  allowErrors.push(resourceErrors)
  installPages(api)
  api.outage = { status: 500 }
  await page.goto('/ui/diagnostics')
  await expect(page.getByText('Could not load system details', { exact: false })).toBeVisible()
  api.outage = null
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByRole('heading', { name: 'Database' })).toBeVisible()

  api.outage = { status: 500 }
  await page.goto('/ui/logs')
  await expect(page.getByRole('heading', { name: 'Logs unavailable' })).toBeVisible()
  api.outage = null
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByText('INFO webui started')).toBeVisible()
})

test('the runs list recovers on reload when the backend comes back', async ({ page, api, allowErrors }) => {
  allowErrors.push(resourceErrors)
  installPages(api)
  api.outage = { status: 500 }
  await page.goto('/ui/runs')
  await expect(page.getByRole('heading', { level: 1, name: 'Runs' })).toBeVisible()
  await expect(page.getByText('#3', { exact: true })).toHaveCount(0)
  api.outage = null
  await page.reload()
  await expect(page.getByText('#3', { exact: true })).toBeVisible()
})

test('a refused WebSocket shows Connecting… and then Offline after INITIAL_OFFLINE_MS', async ({ page, ws, allowErrors }) => {
  allowErrors.push(refusedSocket)
  await ws.setRefuse(true)
  await page.goto('/ui/runs')
  await expect(page.getByText(LABEL).first()).toHaveText('Connecting…')
  // INITIAL_OFFLINE_MS = 12 s, RECONNECT_DELAY_MS = 2 s (useWebSocket.ts).
  await expect(page.getByText(LABEL).first()).toHaveText('Offline', { timeout: 16_000 })
})

test('when a refused WebSocket is accepted again the shell goes Live without a reload', async ({ page, ws, allowErrors }) => {
  allowErrors.push(refusedSocket)
  await ws.setRefuse(true)
  await page.goto('/ui/runs')
  await expect(page.getByText(LABEL).first()).toHaveText('Connecting…')
  await page.waitForTimeout(3000)
  expect(ws.openCount).toBe(0)
  await ws.setRefuse(false)
  await expect(page.getByText(LABEL).first()).toHaveText('Live', { timeout: 6000 })
  expect(ws.openCount).toBe(1)
})

test('a dropped live socket shows Reconnecting… and reconnects', async ({ page, ws }) => {
  await page.goto('/ui/runs')
  await ws.waitForOpen()
  await expect(page.getByText(LABEL).first()).toHaveText('Live')
  await ws.closeAll()
  await expect(page.getByText(LABEL).first()).toHaveText('Reconnecting…')
  await expect(page.getByText(LABEL).first()).toHaveText('Live', { timeout: 6000 })
  expect(ws.connections).toBe(2)
})
