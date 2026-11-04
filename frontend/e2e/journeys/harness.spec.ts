/**
 * Self-tests for the fixtures: each check must catch what it claims to catch.
 * Every test provokes one violation, asserts the fixture recorded it, then clears it so the
 * shared teardown check passes.
 */
import { test, expect } from '../fixtures'

test('harness: an /api request with no handler is recorded as unexpected', async ({ page, api, allowErrors }) => {
  allowErrors.push({ pattern: /Failed to load resource: .*404/, reason: 'the provoked unfaked request answers 404' })
  await page.goto('/ui/runs')
  await page.evaluate(() => fetch('/api/stats').catch(() => undefined))
  await expect.poll(() => api.unexpected).toContain('GET /api/stats')
  api.unexpected.length = 0
})

test('harness: a fixture body that breaks the documented schema is recorded', async ({ page, api }) => {
  // ConfigResponse.embedding_map_enabled is a boolean in openapi.json.
  api.on('GET', '/api/config', { json: { embedding_map_enabled: 'yes' } })
  await page.goto('/ui/runs')
  await expect.poll(() => api.schemaErrors.join('\n')).toContain('/embedding_map_enabled')
  api.schemaErrors.length = 0
})

test('harness: faking an endpoint that is not in openapi.json throws', async ({ api }) => {
  expect(() => api.on('GET', '/api/not-a-real-endpoint', { json: {} })).toThrow(/not in openapi\.json/)
})

test('harness: a request that leaves the preview origin is blocked and recorded', async ({ page, externalRequests, allowErrors }) => {
  allowErrors.push({ pattern: /ERR_BLOCKED_BY_CLIENT/, reason: 'the provoked cross-origin request is aborted by the guard' })
  await page.goto('/ui/runs')
  await page.evaluate(() => fetch('http://127.0.0.1:7860/api/health').catch(() => undefined))
  await expect.poll(() => externalRequests).toContain('http://127.0.0.1:7860/api/health')
  externalRequests.length = 0
})

test('harness: the WebSocket is faked and messages reach the page', async ({ page, ws }) => {
  await page.goto('/ui/runs')
  await ws.waitForOpen()
  await page.evaluate(() => {
    ;(window as unknown as { __got: string[] }).__got = []
    const s = new WebSocket(`ws://${location.host}/ws/updates`)
    s.onmessage = (e) => (window as unknown as { __got: string[] }).__got.push(String(e.data))
  })
  await expect.poll(() => ws.openCount).toBeGreaterThanOrEqual(2)
  ws.send({ type: 'probe', data: { n: 1 } })
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __got: string[] }).__got))
    .toContainEqual(JSON.stringify({ type: 'probe', data: { n: 1 } }))
})
