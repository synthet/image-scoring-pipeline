/**
 * UI E2E (Playwright) — browser tests for the /ui/ SPA.
 *
 * Tier 1 (default): hermetic. `vite preview` serves the e2e build (e2e/.build, never
 * ../static/app) with no proxy; every backend call is faked in the browser (fixtures.ts).
 * Tier 2 (UI_E2E_LIVE=1): see live/ and docs/guides/UI_E2E_TESTING.md.
 *
 * One worker: other sessions run Playwright suites on the same machine.
 */
import { defineConfig, devices } from '@playwright/test'

const PORT = Number(process.env.UI_E2E_PORT || 4517)
const BASE_URL = `http://127.0.0.1:${PORT}`
const LIVE = process.env.UI_E2E_LIVE === '1'

const desktop = {
  ...devices['Desktop Chrome'],
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
  colorScheme: 'dark' as const,
}

export default defineConfig({
  testDir: '.',
  testMatch: LIVE ? ['live/**/*.spec.ts'] : ['journeys/**/*.spec.ts'],
  outputDir: './test-results',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: Boolean(process.env.CI),
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never', outputFolder: './playwright-report' }]] : 'list',
  use: {
    // No browser window, so a run never takes focus from the desktop. `--headed` overrides this.
    headless: true,
    baseURL: LIVE ? process.env.UI_E2E_LIVE_URL : BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'desktop-chromium', use: desktop }],
  webServer: LIVE
    ? undefined
    : {
        command: `npx vite preview --config e2e/vite.e2e.config.ts`,
        cwd: '..',
        url: `${BASE_URL}/ui/`,
        reuseExistingServer: false,
        timeout: 60_000,
        env: { UI_E2E_PORT: String(PORT) },
      },
})
