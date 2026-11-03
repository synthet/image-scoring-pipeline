/**
 * Vite config for the UI E2E suite only.
 *
 * - Builds into e2e/.build (git-ignored). The normal build writes to ../static/app, which is
 *   tracked and served by the developer's running WebUI, so the suite must never use it.
 * - Removes every proxy. Vite's preview server inherits server.proxy, which forwards /api and
 *   /ws to localhost:7860 (the developer's live instance). With no proxy, a request the test
 *   did not fake gets a 404 from the preview server instead of reaching a real backend.
 */
import { defineConfig, mergeConfig, type UserConfig } from 'vite'
import baseConfig from '../vite.config'

export const E2E_OUT_DIR = 'e2e/.build'

export default defineConfig(() => {
  // ../vite.config exports a plain config object.
  const merged = mergeConfig(baseConfig as UserConfig, {
    build: { outDir: E2E_OUT_DIR, emptyOutDir: true },
  }) as UserConfig
  // mergeConfig deep-merges objects, so the proxies are replaced after the merge.
  merged.server = { ...merged.server, proxy: {} }
  merged.preview = {
    ...merged.preview,
    proxy: {},
    host: '127.0.0.1',
    port: Number(process.env.UI_E2E_PORT || 4517),
    strictPort: true,
  }
  return merged
})
