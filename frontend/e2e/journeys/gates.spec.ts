/**
 * Journey 2 — feature gates. GET /api/config drives two routes and their nav entries:
 * embedding_map_enabled → /embeddings ("Atlas"), db_explorer_enabled → /db ("DB").
 */
import type { Page } from '@playwright/test'
import { test, expect, type ApiFake } from '../fixtures'
import { config, installPages } from '../builders'

function withGates(api: ApiFake, embedding_map_enabled: boolean, db_explorer_enabled: boolean) {
  installPages(api)
  api.on('GET', '/api/config', { json: config({ embedding_map_enabled, db_explorer_enabled }) })
  if (embedding_map_enabled) {
    api
      .on('GET', '/api/embedding_spaces', {
        json: {
          success: true,
          message: 'ok',
          data: { spaces: [{ code: 'mobilenet_v2_1280', dim: 1280, description: null, active: true, is_default: true }] },
        },
      })
      .on('GET', '/api/embedding_map', {
        json: { success: true, message: 'ok', data: { points: [], meta: { count: 0, method: 'umap', embedding_space: 'mobilenet_v2_1280', pca_dim: 50 } } },
      })
  }
}

const nav = (page: Page) => page.getByRole('navigation')

test('with both gates off, /db and /embeddings redirect to /runs and their nav entries are hidden', async ({ page, api }) => {
  withGates(api, false, false)
  await page.goto('/ui/runs')
  await expect(nav(page).getByRole('link', { name: 'Runs' })).toBeVisible()
  await expect(nav(page).getByRole('link', { name: 'DB' })).toHaveCount(0)
  await expect(nav(page).getByRole('link', { name: 'Atlas' })).toHaveCount(0)

  for (const route of ['/ui/db', '/ui/db/images', '/ui/embeddings']) {
    await page.goto(route)
    await expect(page).toHaveURL(/\/ui\/runs$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Runs' })).toBeVisible()
  }
})

test('with both gates on, /db and /embeddings render and their nav entries are shown', async ({ page, api }) => {
  withGates(api, true, true)
  await page.goto('/ui/runs')
  await expect(nav(page).getByRole('link', { name: 'DB' })).toBeVisible()
  await expect(nav(page).getByRole('link', { name: 'Atlas' })).toBeVisible()

  await nav(page).getByRole('link', { name: 'DB' }).click()
  await expect(page).toHaveURL(/\/ui\/db$/)
  await expect(page.getByText('Read-only SQL explorer', { exact: false })).toBeVisible()

  await nav(page).getByRole('link', { name: 'Atlas' }).click()
  await expect(page).toHaveURL(/\/ui\/embeddings$/)
  await expect(page.getByText('No embedding points to display')).toBeVisible()
})

test('db_explorer_enabled defaults to on when /api/config omits it', async ({ page, api }) => {
  installPages(api)
  api.on('GET', '/api/config', { json: { enable_culling: false, embedding_map_enabled: false } })
  await page.goto('/ui/db')
  await expect(page).toHaveURL(/\/ui\/db$/)
  await expect(nav(page).getByRole('link', { name: 'DB' })).toBeVisible()
})
