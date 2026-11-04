/**
 * Journey 7 — accessibility.
 *
 * axe-core (WCAG 2.1 A + AA) on each main page in its loaded state. The scan is strict: a rule
 * outside the page's KNOWN baseline fails, and so does a known rule that spreads to more
 * elements than recorded. Each known problem also has a test.fail that turns red once it is
 * fixed, so the baseline gets trimmed.
 *
 * Keyboard: Tab order on the Runs page, and modal focus handling. There is no command palette
 * or hotkey handling to test: `cmdk` and `react-hotkeys-hook` are dependencies but unused.
 */
import AxeBuilder from '@axe-core/playwright'
import type { Page } from '@playwright/test'
import { test, expect } from '../fixtures'
import { config, installPages } from '../builders'

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

type Baseline = Record<string, { issue: string; maxNodes: number }>
const NAMES = '#776'
const CONTRAST = '#777'

/** Page → route and known violations (rule → issue, element count observed 2026-11-02). */
const PAGES: Record<string, { route: string; known: Baseline }> = {
  'runs list': { route: '/ui/runs', known: { 'button-name': { issue: NAMES, maxNodes: 1 }, 'color-contrast': { issue: CONTRAST, maxNodes: 4 } } },
  'run detail': { route: '/ui/runs/3', known: { 'button-name': { issue: NAMES, maxNodes: 1 }, 'color-contrast': { issue: CONTRAST, maxNodes: 22 } } },
  images: { route: '/ui/images', known: { 'color-contrast': { issue: CONTRAST, maxNodes: 8 } } },
  'image inspector': {
    route: '/ui/images/1',
    known: { 'color-contrast': { issue: CONTRAST, maxNodes: 5 }, 'link-in-text-block': { issue: NAMES, maxNodes: 1 } },
  },
  folder: { route: '/ui/folder/1', known: { 'button-name': { issue: NAMES, maxNodes: 1 }, 'color-contrast': { issue: CONTRAST, maxNodes: 10 } } },
  keywords: { route: '/ui/keywords', known: { 'color-contrast': { issue: CONTRAST, maxNodes: 3 } } },
  birds: { route: '/ui/birds', known: { 'color-contrast': { issue: CONTRAST, maxNodes: 3 } } },
  diagnostics: { route: '/ui/diagnostics', known: { 'color-contrast': { issue: CONTRAST, maxNodes: 4 } } },
  logs: { route: '/ui/logs', known: { 'color-contrast': { issue: CONTRAST, maxNodes: 12 } } },
}

const evidence404 = { pattern: /Failed to load resource: .*404/, reason: 'evidence manifest left unfaked on the inspector' }

async function scan(page: Page, route: string) {
  await page.goto(route)
  await page.waitForLoadState('networkidle')
  return new AxeBuilder({ page }).withTags(TAGS).analyze()
}

for (const [name, { route, known }] of Object.entries(PAGES)) {
  test(`axe: ${name} has no accessibility violations beyond its known baseline`, async ({ page, api, allowErrors }) => {
    allowErrors.push(evidence404)
    installPages(api)
    api.allowUnhandled('GET', '/api/images/{image_id}/evidence')
    const { violations } = await scan(page, route)
    const unexpected = violations
      .filter((v) => !known[v.id] || v.nodes.length > known[v.id].maxNodes)
      .map((v) => `${v.id} (${v.impact}) ×${v.nodes.length}${known[v.id] ? ` > baseline ${known[v.id].maxNodes}` : ''}: ${v.nodes[0]?.target.join(' ')}`)
    expect(unexpected, `${route}: new accessibility violations`).toEqual([])
  })
}

for (const [rule, issue] of [['button-name', NAMES], ['link-in-text-block', NAMES], ['color-contrast', CONTRAST]] as const) {
  test(`axe: no page fails ${rule}`, async ({ page, api, allowErrors }) => {
    test.fail(true, `${issue}: ${rule} violations on the main pages`)
    allowErrors.push(evidence404)
    installPages(api)
    api.allowUnhandled('GET', '/api/images/{image_id}/evidence')
    for (const [name, { route, known }] of Object.entries(PAGES)) {
      if (!known[rule]) continue
      const { violations } = await scan(page, route)
      expect.soft(violations.filter((v) => v.id === rule).length, `${name}: ${rule}`).toBe(0)
    }
  })
}

// ─── Keyboard ────────────────────────────────────────────────────────────

const active = (page: Page) =>
  page.evaluate(() => {
    const a = document.activeElement as HTMLElement | null
    if (!a || a === document.body) return null
    const r = a.getBoundingClientRect()
    return {
      tag: a.tagName,
      name: (a.getAttribute('aria-label') ?? a.textContent ?? '').trim().slice(0, 40),
      visible: r.width > 0 && r.height > 0,
      inDialog: Boolean(a.closest('[role="dialog"]')),
    }
  })

test('Tab moves through the Runs page controls in order without getting stuck', async ({ page, api }) => {
  installPages(api)
  await page.goto('/ui/runs')
  await expect(page.getByText('#3', { exact: true })).toBeVisible()
  // Tab until focus leaves the page (after the last control it moves to the browser UI).
  const stops: string[] = []
  for (let i = 0; i < 60; i++) {
    await page.keyboard.press('Tab')
    const a = await active(page)
    if (!a) break
    expect(a.visible, `Tab stop ${i + 1} (${a.tag} "${a.name}") is not visible`).toBe(true)
    stops.push(`${a.tag}:${a.name}`)
  }
  expect(stops.length, 'focus never left the page — a keyboard trap').toBeLessThan(60)
  // Navigation comes before page content, and the page's own primary action is reachable.
  const navRuns = stops.indexOf('A:Runs')
  const newRun = stops.findIndex((s) => s === 'BUTTON:New Run')
  expect(navRuns).toBeGreaterThanOrEqual(0)
  expect(newRun).toBeGreaterThan(navRuns)
  expect(new Set(stops).size, 'focus cycles inside a small trap').toBeGreaterThan(10)
})

test('the diagnostic overlays dialog takes focus, closes on Escape and returns focus to its trigger', async ({ page, api, allowErrors }) => {
  allowErrors.push(evidence404)
  installPages(api)
  api.allowUnhandled('GET', '/api/images/{image_id}/evidence')
  await page.goto('/ui/images/1')
  const trigger = page.getByRole('button', { name: 'More diagnostics' }).first()
  await trigger.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog', { name: 'Diagnostic overlays' })).toBeVisible()
  await expect.poll(async () => (await active(page))?.inDialog).toBe(true)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: 'Diagnostic overlays' })).toHaveCount(0)
  await expect(trigger).toBeFocused()
})

test('the Atlas projection settings dialog keeps Tab inside, closes on Escape and returns focus', async ({ page, api }) => {
  installPages(api)
  api
    .on('GET', '/api/config', { json: config({ embedding_map_enabled: true }) })
    .on('GET', '/api/embedding_spaces', {
      json: { success: true, message: 'ok', data: { spaces: [{ code: 'mobilenet_v2_1280', dim: 1280, description: null, active: true, is_default: true }] } },
    })
    .on('GET', '/api/embedding_map', {
      json: { success: true, message: 'ok', data: { points: [], meta: { count: 0, method: 'umap', embedding_space: 'mobilenet_v2_1280', pca_dim: 50 } } },
    })
  await page.goto('/ui/embeddings')
  const trigger = page.getByRole('button', { name: 'Settings' })
  await trigger.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog')).toBeVisible()
  // Tab past the last control so the wrap-around (the trap) is exercised.
  const focusables = await page
    .getByRole('dialog')
    .evaluate((d) => d.querySelectorAll('button, input, select, textarea, a[href], [tabindex]:not([tabindex="-1"])').length)
  for (let i = 0; i < focusables + 3; i++) {
    await page.keyboard.press('Tab')
    expect((await active(page))?.inDialog, `Tab ${i + 1} of ${focusables + 3} left the dialog`).toBe(true)
  }
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(trigger).toBeFocused()
})

for (const [trigger, closesOnEscape] of [['New Run', true], ['Drive to Complete', false]] as const) {
  test(`the ${trigger} modal is a dialog that takes focus, keeps Tab inside, and returns focus on Escape`, async ({ page, api }) => {
    test.fail(true, `#778: ${trigger} has no dialog role or focus management${closesOnEscape ? '' : ' and ignores Escape'}`)
    installPages(api)
    await page.goto('/ui/runs')
    const button = page.getByRole('main').getByRole('button', { name: trigger }).first()
    await button.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect.poll(async () => (await active(page))?.inDialog).toBe(true)
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press('Tab')
      expect((await active(page))?.inDialog, `Tab ${i + 1} left the modal`).toBe(true)
    }
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(button).toBeFocused()
  })
}
