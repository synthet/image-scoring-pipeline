/**
 * Journey 8 — layout and scaling at 1440×900, 1280×800, 1024×768 and 900×700, each at
 * deviceScaleFactor 1 and 1.5:
 * - no horizontal page overflow (1–2 px of rounding allowed at fractional scales);
 * - header controls inside the viewport and not covered (document.elementFromPoint);
 * - the folder sidebar can be closed and opened again, its toggle reachable both times;
 * - a screenshot per screen and width, attached to the report (no committed baselines: Windows
 *   baselines would fail the Linux CI job, so visual comparison is left out — see the guide).
 */
import type { Locator, Page } from '@playwright/test'
import { test, expect } from '../fixtures'
import { installPages } from '../builders'

const SIZES = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 1024, height: 768 },
  { width: 900, height: 700 },
] as const
const SCALES = [1, 1.5] as const
const SCREENS: [string, string][] = [
  ['runs', '/ui/runs'],
  ['run-detail', '/ui/runs/3'],
  ['dashboard', '/ui/dashboard'],
  ['images', '/ui/images'],
  ['inspector', '/ui/images/1'],
  ['folder', '/ui/folder/1'],
  ['keywords', '/ui/keywords'],
  ['diagnostics', '/ui/diagnostics'],
  ['logs', '/ui/logs'],
]
const HEADER_OVERFLOW = '#781: the header overflows by 8 px at 900 px (live status pushed off-screen)'

async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
}

/** Fully inside the viewport, and the topmost element at its centre is itself (or a child). */
async function reachable(locator: Locator): Promise<string | null> {
  return locator.evaluate((el) => {
    const r = el.getBoundingClientRect()
    const W = document.documentElement.clientWidth
    const H = document.documentElement.clientHeight
    if (r.width === 0 || r.height === 0) return 'not rendered'
    if (r.left < 0 || r.top < 0 || r.right > W + 0.5 || r.bottom > H + 0.5)
      return `outside the viewport (${Math.round(r.left)},${Math.round(r.top)})–(${Math.round(r.right)},${Math.round(r.bottom)}) of ${W}×${H}`
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)
    return hit && (hit === el || el.contains(hit)) ? null : `covered by <${hit?.tagName.toLowerCase()}>`
  })
}

const toggle = (page: Page) => page.getByRole('button', { name: 'Toggle folder sidebar' })

for (const size of SIZES) {
  for (const scale of SCALES) {
    test.describe(`${size.width}×${size.height} @${scale}x`, () => {
      test.use({ viewport: size, deviceScaleFactor: scale })
      const tolerance = scale === 1 ? 0 : 2

      test('main screens have no horizontal page overflow', async ({ page, api, allowErrors }, testInfo) => {
        test.fail(size.width === 900, HEADER_OVERFLOW)
        allowErrors.push({ pattern: /Failed to load resource: .*404/, reason: 'evidence manifest left unfaked on the inspector' })
        installPages(api)
        api.allowUnhandled('GET', '/api/images/{image_id}/evidence')
        for (const [name, route] of SCREENS) {
          await page.goto(route)
          await page.waitForLoadState('networkidle')
          await testInfo.attach(`${name}-${size.width}x${size.height}@${scale}x.png`, {
            body: await page.screenshot(),
            contentType: 'image/png',
          })
          expect.soft(await horizontalOverflow(page), `${name}: horizontal overflow (px)`).toBeLessThanOrEqual(tolerance)
        }
      })

      test('header controls are inside the viewport and not covered', async ({ page, api }) => {
        test.fail(size.width === 900, HEADER_OVERFLOW)
        installPages(api)
        await page.goto('/ui/runs')
        await expect(page.getByText('#3', { exact: true })).toBeVisible()
        const nav = page.getByRole('navigation')
        const controls: [string, Locator][] = [
          ['sidebar toggle', toggle(page)],
          ...(['Runs', 'Dashboard', 'Images', 'Birds', 'Keywords', 'Health', 'Logs'] as const).map(
            (n) => [`nav ${n}`, nav.getByRole('link', { name: n })] as [string, Locator],
          ),
          ['connection status', page.getByText(/^(Live|Connecting…|Reconnecting…|Offline)$/).first()],
          ['New Run', page.getByRole('main').getByRole('button', { name: 'New Run' }).first()],
        ]
        for (const [label, locator] of controls) expect.soft(await reachable(locator), label).toBeNull()
      })

      test('the folder sidebar closes and opens again, its toggle reachable both times', async ({ page, api }) => {
        installPages(api)
        await page.goto('/ui/runs')
        const tree = page.getByText('Photos', { exact: true }).first()
        await expect(tree).toBeVisible()
        expect(await reachable(toggle(page))).toBeNull()
        await toggle(page).click()
        await expect(tree).toBeHidden()
        expect(await reachable(toggle(page)), 'toggle after closing').toBeNull()
        await toggle(page).click()
        await expect(tree).toBeVisible()
        expect(await reachable(toggle(page)), 'toggle after opening').toBeNull()
      })
    })
  }
}
