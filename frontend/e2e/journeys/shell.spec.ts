/**
 * Journey 1 — startup and shell: every route in App.tsx renders against faked data with no
 * page or console error, redirects land where App.tsx says, and deep links survive a reload.
 */
import type { Page } from '@playwright/test'
import { test, expect } from '../fixtures'
import { installPages } from '../builders'

type Check = (page: Page) => Promise<void>
const heading = (name: string | RegExp): Check => async (page) => {
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
}
const text = (value: string): Check => async (page) => {
  await expect(page.getByText(value, { exact: true }).first()).toBeVisible()
}

/** Route → what proves the page rendered its own content (not just the shell). */
const ROUTES: [string, Check][] = [
  ['/ui/runs', heading('Runs')],
  ['/ui/runs/3', heading('Run #3')],
  ['/ui/dashboard', heading('Dashboard')],
  ['/ui/images', text('DSC_0001.NEF')],
  ['/ui/images/2', text('DSC_0002.NEF')],
  ['/ui/folder/1', heading('2026-10-01')],
  ['/ui/stacks/1', heading('Stack 1')],
  ['/ui/birds', heading('Birds')],
  ['/ui/birds/Grey%20Heron', heading('Grey Heron')],
  ['/ui/keywords', heading('Keywords')],
  ['/ui/keywords/bird', heading('bird')],
  ['/ui/diagnostics', heading('Health')],
  ['/ui/logs', heading('Logs')],
]

for (const [route, check] of ROUTES) {
  test(`route ${route} renders its content without errors`, async ({ page, api }) => {
    installPages(api)
    await page.goto(route)
    await check(page)
    await expect(page).toHaveURL(new RegExp(`${route.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`))
  })
}

const REDIRECTS: [string, string][] = [
  ['/ui/', '/ui/runs'],
  ['/ui/scores/anything', '/ui/runs'],
  ['/ui/map/anything', '/ui/runs'],
  ['/ui/settings', '/ui/diagnostics'],
]

for (const [from, to] of REDIRECTS) {
  test(`${from} redirects to ${to}`, async ({ page, api }) => {
    installPages(api)
    await page.goto(from)
    await expect(page).toHaveURL(new RegExp(`${to}$`))
  })
}

for (const [route, check] of [ROUTES[1], ROUTES[4], ROUTES[8]]) {
  test(`deep link ${route} survives a reload`, async ({ page, api }) => {
    installPages(api)
    await page.goto(route)
    await check(page)
    await page.reload()
    await check(page)
    await expect(page).toHaveURL(new RegExp(`${route.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`))
  })
}
