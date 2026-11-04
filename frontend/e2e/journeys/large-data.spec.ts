/**
 * Journey 9 — large data. The routed Images page is a server-paged table (25/50/100 rows;
 * components/images/ImageBrowsePanel.tsx), not a virtualized list — the virtualized
 * pages/GalleryPage.tsx has no route. So "bounded rendering" means one page of rows in the DOM.
 *
 * Budget: first row visible ≤ FIRST_ROW_BUDGET_MS after navigation with 5,000 images.
 * Measured 2026-11-02 on the dev machine: 653–790 ms (6 loads). The budget leaves ~4× headroom for
 * a shared, loaded machine (the gallery suite saw 0.2–0.9 s idle and 2.6 s under load).
 */
import type { Page } from '@playwright/test'
import { test, expect } from '../fixtures'
import { image, installPages } from '../builders'

const TOTAL = 5000
const FIRST_ROW_BUDGET_MS = 3000
const images = () => Array.from({ length: TOTAL }, (_, i) => image(i + 1))
const idLink = (page: Page, id: number) => page.getByRole('link', { name: String(id), exact: true })
const rows = (page: Page) => page.locator('tbody tr')

async function setPageSize(page: Page, size: 25 | 50 | 100) {
  await page.getByRole('combobox', { name: /Page size/ }).selectOption(String(size))
  await expect(rows(page)).toHaveCount(size)
}

test(`with ${TOTAL} images the Images page renders one bounded page of rows`, async ({ page, api }) => {
  installPages(api, images())
  await page.goto('/ui/images')
  await expect(rows(page)).toHaveCount(50)
  await expect(page.getByText(`Page 1 / ${TOTAL / 50}`)).toBeVisible()
  await setPageSize(page, 100)
  await expect(page.getByText(`Page 1 / ${TOTAL / 100}`)).toBeVisible()
  const req = api.calls('GET', '/api/images').at(-1)!
  expect(new URL(req.path, 'http://x').searchParams.get('page_size')).toBe('100')
})

test(`the first row appears within ${FIRST_ROW_BUDGET_MS} ms with ${TOTAL} images`, async ({ page, api }, testInfo) => {
  installPages(api, images())
  const t0 = Date.now()
  await page.goto('/ui/images')
  await idLink(page, 1).waitFor()
  const elapsed = Date.now() - t0
  testInfo.annotations.push({ type: 'first-row-ms', description: String(elapsed) })
  expect(elapsed).toBeLessThanOrEqual(FIRST_ROW_BUDGET_MS)
})

test('mouse-wheel scrolling reaches the last row of a 100-row page', async ({ page, api }) => {
  installPages(api, images())
  await page.goto('/ui/images')
  await setPageSize(page, 100)
  const last = idLink(page, 100)
  await expect(last).not.toBeInViewport()
  // Wheel over the table, as a user would (setting scrollTop directly can skip scroll handlers).
  await rows(page).first().hover()
  for (let i = 0; i < 40 && !(await last.isVisible() && (await last.evaluate((el) => el.getBoundingClientRect().bottom <= window.innerHeight))); i++) {
    await page.mouse.wheel(0, 600)
  }
  await expect(last).toBeInViewport()
})

test(`the last of ${TOTAL} images is reachable through the pager`, async ({ page, api }) => {
  test.setTimeout(120_000)
  installPages(api, images())
  await page.goto('/ui/images')
  await setPageSize(page, 100)
  const next = page.getByRole('button', { name: 'Next', exact: true })
  for (let p = 2; p <= TOTAL / 100; p++) {
    await next.click()
    await expect(page.getByText(`Page ${p} / ${TOTAL / 100}`)).toBeVisible()
  }
  await expect(idLink(page, TOTAL)).toBeAttached()
  await expect(next).toBeDisabled()
})

test('large libraries: a last-page jump, select-all and keyboard row navigation exist', async ({ page, api }) => {
  test.fail(true, '#782: Prev/Next only, no row selection or select-all, no keyboard row navigation')
  installPages(api, images())
  await page.goto('/ui/images')
  await expect(rows(page)).toHaveCount(50)
  await expect.soft(page.getByRole('button', { name: /^Last/ }), 'jump to the last page').toHaveCount(1)
  await expect.soft(page.getByRole('checkbox', { name: /select all/i }), 'select-all').toHaveCount(1)
  await idLink(page, 1).focus()
  await page.keyboard.press('ArrowDown')
  await expect.soft(idLink(page, 2), 'ArrowDown moves to the next row').toBeFocused()
})
