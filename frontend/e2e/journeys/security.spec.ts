/**
 * Journey 6 — security.
 * - Text from the API (keywords, folder names, log lines, image fields, error messages) renders
 *   as text and never runs. The SPA has no HTML sinks today (no dangerouslySetInnerHTML /
 *   innerHTML / markdown), so these are regression guards.
 * - Image endpoints are requested only with paths the API supplied.
 * - Links that open a new tab carry rel="noopener noreferrer" (none exist today).
 * The built-bundle credential scan is scripts/ci/check_secrets.py, which scans every tracked
 * file including static/app/assets/*.js (see docs/guides/UI_E2E_TESTING.md).
 */
import type { Page } from '@playwright/test'
import { test, expect } from '../fixtures'
import { folderDetail, image, installPages, keywordCloud, logTails, dbBackend } from '../builders'

// Payloads without "/" so they also fit inside a path segment.
const IMG = '<img src=xss-probe onerror=window.__xss=1>'
const SVG = '<svg onload=window.__xss=1>'
const SCRIPT = '<script>window.__xss=1</script>'

async function trackProbe(page: Page): Promise<string[]> {
  const hits: string[] = []
  page.on('request', (r) => r.url().includes('xss-probe') && hits.push(r.url()))
  return hits
}

async function expectInert(page: Page, probeHits: string[]) {
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined()
  expect(probeHits, 'an injected <img> was turned into a real element').toEqual([])
}

test('keywords and folder names from the API render as text and never run', async ({ page, api }) => {
  const hits = await trackProbe(page)
  installPages(api)
  api
    .on('GET', '/api/keywords/cloud', { json: keywordCloud('general', [[`heron ${IMG}`, 9], [`kingfisher ${SCRIPT}`, 3]]) })
    .on('GET', '/api/folders/{folder_id}', ({ params }) => ({ json: folderDetail(Number(params.folder_id), { path: `/mnt/d/Photos/${SVG}` }) }))
  await page.goto('/ui/keywords')
  await expect(page.getByText(`heron ${IMG}`)).toBeVisible()
  await expect(page.getByText(`kingfisher ${SCRIPT}`)).toBeVisible()
  await page.goto('/ui/folder/1')
  await expect(page.getByRole('heading', { level: 1, name: SVG })).toBeVisible()
  await expectInert(page, hits)
})

test('log lines from the Logs page and the live run log render as text and never run', async ({ page, api, ws }) => {
  const hits = await trackProbe(page)
  installPages(api)
  api.onUndocumented('GET', '/api/status/log-tails', '#770', { json: logTails([`ERROR boom ${IMG}`, `INFO ${SCRIPT}`]) })
  await page.goto('/ui/logs')
  await expect(page.getByText(`ERROR boom ${IMG}`)).toBeVisible()
  await expect(page.getByText(`INFO ${SCRIPT}`)).toBeVisible()

  await page.goto('/ui/runs/3')
  await ws.waitForOpen()
  ws.send({ type: 'log_line', data: { run_id: 3, level: 'ERROR', message: `failed ${SVG} ${IMG}`, ts: '2026-10-01T09:00:00Z' } })
  await expect(page.getByText(`failed ${SVG} ${IMG}`)).toBeVisible()
  await expectInert(page, hits)
})

test('image fields and backend error messages render as text and never run', async ({ page, api, allowErrors }) => {
  allowErrors.push({ pattern: /status of 400/, reason: 'the DB explorer step answers 400 on purpose to show an error detail' })
  const hits = await trackProbe(page)
  installPages(api, [image(1, { file_name: `DSC_0001 ${IMG}.NEF`, title: SCRIPT, description: SVG })])
  dbBackend(api, { images: [] })
  await page.goto('/ui/images/1')
  await expect(page.getByText(`DSC_0001 ${IMG}.NEF`).first()).toBeVisible()

  // A backend error detail shown verbatim by the DB explorer.
  api.onUndocumented('POST', '/api/db/query', '#770', { status: 400, json: { detail: `syntax error near ${IMG}` } })
  await page.goto('/ui/db')
  await expect(page.getByText(`syntax error near ${IMG}`, { exact: false }).first()).toBeVisible()
  await expectInert(page, hits)
})

test('image endpoints are requested only with paths the API supplied', async ({ page, api }) => {
  const images = [image(1), image(2), image(3)]
  installPages(api, images)
  const given = new Set(images.flatMap((i) => [i.file_path, i.thumbnail_path].filter(Boolean) as string[]))
  await page.goto('/ui/images')
  await expect(page.getByText('DSC_0001.NEF', { exact: true }).first()).toBeVisible()
  await page.goto('/ui/images/2')
  await expect(page.getByText('DSC_0002.NEF', { exact: true }).first()).toBeVisible()

  const sourceImagePaths = api.requests
    .filter((r) => r.path.startsWith('/source-image'))
    .map((r) => new URL(r.path, 'http://x').searchParams.get('path'))
  expect(sourceImagePaths.length).toBeGreaterThan(0)
  for (const p of sourceImagePaths) expect(given.has(p ?? ''), `unexpected /source-image path ${p}`).toBe(true)

  const imageIds = api.requests.filter((r) => r.template === '/api/images/{image_id}').map((r) => Number(r.path.split('/')[3]))
  for (const id of imageIds) expect(images.map((i) => i.id)).toContain(id)
})

test('links that open a new tab use rel="noopener noreferrer" and no link uses javascript:', async ({ page, api, allowErrors }) => {
  allowErrors.push({ pattern: /Failed to load resource: .*404/, reason: 'evidence manifest left unfaked on the inspector' })
  installPages(api)
  api.allowUnhandled('GET', '/api/images/{image_id}/evidence')
  for (const route of ['/ui/runs', '/ui/runs/3', '/ui/dashboard', '/ui/images', '/ui/images/1', '/ui/folder/1', '/ui/keywords', '/ui/birds', '/ui/diagnostics', '/ui/logs']) {
    await page.goto(route)
    await page.waitForLoadState('networkidle')
    const links = await page.$$eval('a', (as) =>
      as.map((a) => ({ href: a.getAttribute('href') ?? '', target: a.getAttribute('target') ?? '', rel: a.getAttribute('rel') ?? '' })),
    )
    for (const l of links) {
      expect(l.href.trim().toLowerCase().startsWith('javascript:'), `${route}: javascript: link`).toBe(false)
      if (l.target === '_blank') {
        expect(l.rel.split(/\s+/), `${route}: ${l.href} opens a new tab without noopener`).toEqual(expect.arrayContaining(['noopener', 'noreferrer']))
      }
    }
  }
})
