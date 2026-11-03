import { test, expect } from '../fixtures'

test('opening /ui/ lands on the runs list with the active run shown', async ({ page, api }) => {
  await page.goto('/ui/')

  await expect(page).toHaveURL(/\/ui\/runs$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Runs' })).toBeVisible()
  // DEFAULT_RUNS has exactly one running run (#3); the Active tab lists it.
  await expect(page.getByText('#3', { exact: true })).toBeVisible()
  await expect(page.getByText('#2', { exact: true })).toHaveCount(0)

  expect(api.calls('GET', '/api/config').length).toBeGreaterThan(0)
})
