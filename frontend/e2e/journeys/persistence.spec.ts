/**
 * Journey 5 — persistence. What the product keeps across a reload and a new tab:
 * - diagnostic overlay opacity / background dimming → localStorage (`diagnostic-*`,
 *   hooks/useDiagnostics.ts);
 * - DB explorer table → the URL (/db/:tableName, pages/DbPage.tsx).
 * Everything else (Images filters, sort and page size, the Runs tab, DB page / page size,
 * typed SQL, panel sizes) is component state and resets on reload — listed in the test catalog,
 * not asserted as a defect.
 */
import type { BrowserContext, Page } from '@playwright/test'
import { test, expect, ApiFake, WsFake } from '../fixtures'
import { dbBackend, installBaseline, installPages } from '../builders'

/** A second tab gets its own faked backend (routes are per page). */
async function openFakedTab(context: BrowserContext, baseURL: string | undefined, setup: (api: ApiFake) => void): Promise<Page> {
  const tab = await context.newPage()
  const origin = new URL(baseURL ?? 'http://127.0.0.1').origin
  const api = new ApiFake()
  installBaseline(api)
  setup(api)
  await api.attach(tab, origin)
  await new WsFake().attach(tab, origin)
  return tab
}

const opacity = (page: Page) => page.getByRole('slider', { name: 'Diagnostic overlay opacity' })
const dimming = (page: Page) => page.getByRole('slider', { name: 'Subject background dimming' })

async function openDiagnostics(page: Page) {
  await page.getByRole('button', { name: 'More diagnostics' }).first().click()
  await expect(page.getByRole('dialog', { name: 'Diagnostic overlays' })).toBeVisible()
}

const evidence404 = {
  pattern: /Failed to load resource: the server responded with a status of 404/,
  reason: 'the evidence manifest is deliberately left unfaked (404); this test covers only the slider preferences',
}

test('diagnostic overlay opacity and dimming survive a reload and a new tab', async ({ page, api, context, baseURL, allowErrors }) => {
  allowErrors.push(evidence404)
  installPages(api)
  api.allowUnhandled('GET', '/api/images/{image_id}/evidence')
  await page.goto('/ui/images/1')
  await openDiagnostics(page)
  await expect(opacity(page)).toHaveValue('0.45') // defaults from useDiagnostics.ts
  await opacity(page).fill('0.8')
  await dimming(page).fill('0.2')
  await expect(opacity(page)).toHaveValue('0.8')

  await page.reload()
  await openDiagnostics(page)
  await expect(opacity(page)).toHaveValue('0.8')
  await expect(dimming(page)).toHaveValue('0.2')

  const tab = await openFakedTab(context, baseURL, (a) => {
    installPages(a)
    a.allowUnhandled('GET', '/api/images/{image_id}/evidence')
  })
  await tab.goto('/ui/images/2')
  await openDiagnostics(tab)
  await expect(opacity(tab)).toHaveValue('0.8')
  await expect(dimming(tab)).toHaveValue('0.2')
})

test('the DB explorer keeps the selected table across a reload and a new tab', async ({ page, api, context, baseURL }) => {
  const tables = {
    images: [{ id: 1, file_name: 'DSC_0001.NEF' }, { id: 2, file_name: 'DSC_0002.NEF' }],
    jobs: [{ id: 7, status: 'completed' }],
  }
  installPages(api)
  dbBackend(api, tables)
  await page.goto('/ui/db')
  await page.getByRole('link', { name: 'jobs' }).click()
  await expect(page).toHaveURL(/\/ui\/db\/jobs$/)
  await expect(page.getByRole('cell', { name: 'completed' })).toBeVisible()

  await page.reload()
  await expect(page).toHaveURL(/\/ui\/db\/jobs$/)
  await expect(page.getByRole('cell', { name: 'completed' })).toBeVisible()

  const tab = await openFakedTab(context, baseURL, (a) => {
    installPages(a)
    dbBackend(a, tables)
  })
  await tab.goto(page.url())
  await expect(tab.getByRole('cell', { name: 'completed' })).toBeVisible()
  await expect(tab.getByRole('cell', { name: 'DSC_0001.NEF' })).toHaveCount(0)
})
