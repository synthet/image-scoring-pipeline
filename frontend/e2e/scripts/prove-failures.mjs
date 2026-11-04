#!/usr/bin/env node
/**
 * Fail-path proofs for the UI E2E suite.
 *
 * For each break below: apply it to the product source, rebuild the e2e bundle, run the test
 * that covers that path and require it to FAIL; then restore the file. Every edited file must be
 * unmodified in git before the run and again afterwards. A test must also fail alone: the line
 * reports how many tests failed, which should be 1.
 *
 *   npm run e2e:prove                 all breaks
 *   npm run e2e:prove -- smoke-root   only the named break(s)
 *
 * A break must match its `find` text exactly once, so a refactor that moves the code makes the
 * proof fail loudly instead of silently testing nothing.
 */
import { spawnSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
// Run the tools' Node entry points directly: no shell, so `-g` patterns with spaces stay whole.
const BIN = {
  vite: path.join(FRONTEND, 'node_modules/vite/bin/vite.js'),
  playwright: path.join(FRONTEND, 'node_modules/@playwright/test/cli.js'),
  vitest: path.join(FRONTEND, 'node_modules/vitest/vitest.mjs'),
}
const escapeRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/**
 * runner 'playwright' (default): rebuild the e2e bundle, run tests matching `grep`.
 * runner 'vitest': run `vitestFile` with `-t grep` (no rebuild).
 * @type {{ name: string, file: string, find: string, replace: string, grep: string, runner?: 'playwright'|'vitest', vitestFile?: string }[]}
 */
export const BREAKS = [
  {
    name: 'smoke-root',
    file: 'src/App.tsx',
    find: '<Route index element={<Navigate to="/runs" replace />} />',
    replace: '<Route index element={<Navigate to="/dashboard" replace />} />',
    grep: 'opening /ui/ lands on the runs list',
  },
  // Journey 1 — shell
  {
    name: 'shell-route-wrong-page',
    file: 'src/App.tsx',
    find: '<Route path="/birds" element={<BirdsPage />} />',
    replace: '<Route path="/birds" element={<KeywordsPage />} />',
    grep: 'route /ui/birds renders',
  },
  {
    name: 'shell-settings-redirect',
    file: 'src/App.tsx',
    find: '<Route path="/settings" element={<Navigate to="/diagnostics" replace />} />',
    replace: '<Route path="/settings" element={<Navigate to="/runs" replace />} />',
    grep: '/ui/settings redirects',
  },
  {
    name: 'shell-deep-link-param',
    file: 'src/pages/KeywordImagesPage.tsx',
    find: "const keyword = (rawValue ?? '').trim()",
    replace: "const keyword = encodeURIComponent(rawValue ?? '')",
    grep: 'deep link /ui/birds/Grey%20Heron survives a reload',
  },
  // Journey 2 — gates
  {
    name: 'gates-db-nav-ungated',
    file: 'src/components/layout/Shell.tsx',
    find: '{isDbExplorerEnabled && (',
    replace: '{true && (',
    grep: 'with both gates off',
  },
  {
    name: 'gates-atlas-nav-hidden',
    file: 'src/components/layout/Shell.tsx',
    find: '{isEmbeddingMapEnabled && (',
    replace: '{false && (',
    grep: 'with both gates on',
  },
  {
    name: 'gates-db-default-off',
    file: 'src/hooks/useConfig.ts',
    find: 'isDbExplorerEnabled: config?.db_explorer_enabled ?? true,',
    replace: 'isDbExplorerEnabled: config?.db_explorer_enabled ?? false,',
    grep: 'db_explorer_enabled defaults to on',
  },
  // Journey 3 — runs
  {
    name: 'runs-history-query',
    file: 'src/pages/RunsPage.tsx',
    find: 'history: true,',
    replace: 'history: false,',
    grep: 'runs list shows the running run under Active',
  },
  {
    name: 'runs-progress-ignored',
    file: 'src/utils/adaptBackendMessage.ts',
    find: 'items_done: Number(data.current ?? 0),',
    replace: 'items_done: 0,',
    grep: 'progress pushed over the WebSocket',
  },
  {
    name: 'runs-live-status-no-refetch',
    file: 'src/hooks/useWebSocket.ts',
    find: 'if (bumpRuns) store.bumpRunsVersion()',
    replace: 'void bumpRuns',
    grep: 'a status change pushed live moves the run off Active',
  },
  {
    name: 'runs-log-order',
    file: 'src/stores/wsStore.ts',
    find: 'const next = existing.length >= 500 ? [...existing.slice(1), e] : [...existing, e]',
    replace: 'const next = existing.length >= 500 ? [...existing.slice(1), e] : [e, ...existing]',
    grep: 'run detail shows the run, its stages, and live log lines',
  },
  {
    name: 'runs-cancel-wrong-endpoint',
    file: 'src/pages/RunDetailPage.tsx',
    find: 'const cancelMut = useMutation({ mutationFn: () => runsApi.cancel(id), onSuccess: invalidate })',
    replace: 'const cancelMut = useMutation({ mutationFn: () => runsApi.pause(id), onSuccess: invalidate })',
    grep: 'cancelling a running run sends',
  },
  // Journey 4 — backend unavailable
  {
    name: 'down-blank-not-found',
    file: 'src/pages/RunDetailPage.tsx',
    find: '<p className="text-sm text-[var(--color-danger)]">Run #{id} not found</p>',
    replace: '<p className="text-sm text-[var(--color-danger)]"></p>',
    grep: 'with /api answering 500, no page is blank',
  },
  {
    name: 'down-no-loading-state',
    file: 'src/pages/RunDetailPage.tsx',
    find: '  if (runLoading) {',
    replace: '  if (false) {',
    grep: 'requests that hang leave the shell',
  },
  {
    name: 'down-retry-noop',
    file: 'src/pages/DiagnosticsPage.tsx',
    find: '<Button variant="secondary" onClick={() => refetch()} className="mt-4">',
    replace: '<Button variant="secondary" onClick={() => undefined} className="mt-4">',
    grep: 'Diagnostics and Logs recover through Retry',
  },
  {
    name: 'down-reload-no-data',
    file: 'src/pages/RunsPage.tsx',
    find: "queryFn: () => runsApi.list({ limit: 200, status: 'running,paused,queued,pending' }),",
    replace: 'queryFn: async () => [],',
    grep: 'the runs list recovers on reload',
  },
  {
    name: 'down-ws-no-reconnect-after-refusal',
    file: 'src/hooks/useWebSocket.ts',
    find: 'reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)',
    replace: 'reconnectTimer.current = null',
    grep: 'when a refused WebSocket is accepted again',
  },
  {
    name: 'down-ws-no-reconnect-after-drop',
    file: 'src/hooks/useWebSocket.ts',
    find: 'reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)',
    replace: 'reconnectTimer.current = null',
    grep: 'a dropped live socket shows Reconnecting',
  },
  // Journey 5 — persistence
  {
    name: 'persist-diagnostic-pref-not-saved',
    file: 'src/hooks/useDiagnostics.ts',
    find: 'try { localStorage.setItem(`diagnostic-${name}`, String(clamped)); }',
    replace: 'try { void name; }',
    grep: 'diagnostic overlay opacity and dimming survive',
  },
  {
    name: 'persist-db-table-not-in-url',
    file: 'src/components/db/DbTableSidebar.tsx',
    find: 'to={dbExplorerPath(table)}',
    replace: "to={dbExplorerPath('')}",
    grep: 'the DB explorer keeps the selected table',
  },
  // Journey 6 — security (each break adds a real HTML sink or a bad request)
  {
    name: 'sec-keyword-html-sink',
    file: 'src/components/keywords/TagCloud.tsx',
    find: '            {label}',
    replace: '            <span dangerouslySetInnerHTML={{ __html: label }} />',
    grep: 'keywords and folder names from the API render as text',
  },
  {
    // The Logs page renders messages through LogMessageWithImageLinks (components/ui/
    // StatusLogFilePanel.tsx); components/logs/StatusLogFilePanel.tsx is an unused copy.
    name: 'sec-log-html-sink',
    file: 'src/utils/logMessageLinks.tsx',
    find: '<span key={i}>{s.text}</span>',
    replace: '<span key={i} dangerouslySetInnerHTML={{ __html: s.text }} />',
    grep: 'log lines from the Logs page and the live run log',
  },
  {
    name: 'sec-image-foreign-path',
    file: 'src/pages/ImageInspectorPage.tsx',
    find: 'if (full) return `/source-image?path=${encodeURIComponent(full)}`',
    replace: "if (full) return '/source-image?path=%2Fetc%2Fpasswd'",
    grep: 'image endpoints are requested only with paths the API supplied',
  },
  {
    name: 'sec-new-tab-without-rel',
    file: 'src/components/layout/Shell.tsx',
    find: 'to={to}',
    replace: 'to={to} target="_blank"',
    grep: 'links that open a new tab use rel',
  },
  // Journey 7 — accessibility
  {
    name: 'a11y-new-violation-unnamed-nav-link',
    file: 'src/components/layout/Shell.tsx',
    find: 'label="Runs" />',
    replace: 'label="" />',
    grep: 'axe: runs list has no accessibility violations beyond its known baseline',
  },
  {
    name: 'a11y-nav-links-unfocusable',
    file: 'src/components/layout/Shell.tsx',
    find: 'to={to}',
    replace: 'to={to} tabIndex={-1}',
    grep: 'Tab moves through the Runs page controls',
  },
  {
    name: 'a11y-diagnostics-focus-not-returned',
    file: 'src/components/Diagnostics/DiagnosticControls.tsx',
    find: "root.current?.querySelector('button')?.focus();",
    replace: 'void 0;',
    grep: 'the diagnostic overlays dialog takes focus',
  },
  {
    // (modal={false} is not a break: Radix FocusScope loops Tab even for non-modal dialogs.)
    name: 'a11y-atlas-dialog-focus-not-returned',
    file: 'src/features/embedding-atlas/components/ProjectionSettingsDialog.tsx',
    find: '<Dialog.Content className=',
    replace: '<Dialog.Content onCloseAutoFocus={(e) => e.preventDefault()} className=',
    grep: 'the Atlas projection settings dialog keeps Tab inside',
  },
  // Journey 8 — layout (representative size: 1440×900 @1x)
  {
    name: 'layout-wide-header',
    file: 'src/components/layout/Shell.tsx',
    find: 'flex h-12 items-center gap-3',
    replace: 'flex h-12 min-w-[1500px] items-center gap-3',
    grep: '1440×900 @1x main screens have no horizontal page overflow',
  },
  {
    name: 'layout-status-off-screen',
    file: 'src/components/layout/ConnectionStatus.tsx',
    find: '<div className="flex items-center gap-1.5">',
    replace: '<div className="flex items-center gap-1.5 fixed -right-40">',
    grep: '1440×900 @1x header controls are inside the viewport',
  },
  {
    name: 'layout-sidebar-toggle-noop',
    file: 'src/stores/uiStore.ts',
    find: 'toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),',
    replace: 'toggleSidebar: () => set((s) => ({ sidebarOpen: s.sidebarOpen })),',
    grep: '1440×900 @1x the folder sidebar closes and opens again',
  },
  // Journey 9 — large data
  {
    name: 'ld-unbounded-page',
    file: 'src/components/images/ImageBrowsePanel.tsx',
    find: 'page_size: pageSize,',
    replace: 'page_size: 5000,',
    grep: 'images the Images page renders one bounded page of rows',
  },
  {
    name: 'ld-slow-first-row',
    file: 'src/api/gallery.ts',
    find: 'return api.get<ImageListResponse>(`/images?${q.toString()}`)',
    replace: 'return new Promise((r) => setTimeout(r, 4000)).then(() => api.get<ImageListResponse>(`/images?${q.toString()}`))',
    grep: 'the first row appears within',
  },
  {
    name: 'ld-table-not-scrollable',
    file: 'src/components/images/ImageBrowsePanel.tsx',
    find: '<div className="flex-1 min-h-0 overflow-auto">',
    replace: '<div className="flex-1 min-h-0 overflow-hidden">',
    grep: 'mouse-wheel scrolling reaches the last row',
  },
  {
    name: 'ld-pager-stops-early',
    file: 'src/components/images/ImageBrowsePanel.tsx',
    find: 'const canNext = totalPages > 0 && page < totalPages',
    replace: 'const canNext = totalPages > 0 && page < Math.min(totalPages, 10)',
    grep: 'images is reachable through the pager',
  },
  // Journey 10 — long operations
  {
    name: 'lo-progress-not-stored',
    file: 'src/hooks/useWebSocket.ts',
    find: 'store.setRunProgress(event)',
    replace: 'void event',
    grep: 'live progress climbs to the end',
  },
  {
    name: 'lo-detail-not-invalidated',
    file: 'src/pages/RunDetailPage.tsx',
    find: 'if (runsVersion === 0) return',
    replace: 'if (runsVersion >= 0) return',
    grep: 'a run that fails mid-way shows Failed',
  },
  {
    name: 'lo-cancel-shown-after-cancel',
    file: 'src/pages/RunDetailPage.tsx',
    find: "{(run.status === 'pending' || run.status === 'running' || run.status === 'queued' || run.status === 'paused') && (",
    replace: "{(run.status !== 'completed') && (",
    grep: 'a run cancelled during progress stays Canceled',
  },
  {
    name: 'contract-undocumented-call',
    file: 'src/api/runs.ts',
    find: 'get: (id: number) => api.get<Run>(`/jobs/${id}`),',
    replace: 'get: (id: number) => api.get<Run>(`/jobz/${id}`),',
    grep: 'every call is documented',
    runner: 'vitest',
    vitestFile: 'src/test/contract.test.ts',
  },
  {
    name: 'ws-no-reconnect',
    file: 'src/hooks/useWebSocket.ts',
    find: 'reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)',
    replace: 'reconnectTimer.current = null',
    grep: 'reconnects after a live socket closes',
    runner: 'vitest',
    vitestFile: 'src/hooks/useWebSocket.test.tsx',
  },
]

function run(tool, args) {
  return spawnSync(process.execPath, [BIN[tool], ...args], { cwd: FRONTEND, stdio: 'pipe', encoding: 'utf8', windowsHide: true })
}

function build() {
  const r = run('vite', ['build', '--config', 'e2e/vite.e2e.config.ts'])
  if (r.status !== 0) throw new Error(`e2e build failed:\n${r.stdout}\n${r.stderr}`)
}

/** Every file a break edits must be unmodified in git, before and after. */
function gitClean(files) {
  for (const f of new Set(files)) {
    const r = spawnSync('git', ['diff', '--quiet', '--', f], { cwd: FRONTEND, windowsHide: true })
    if (r.status !== 0) throw new Error(`${f} has uncommitted changes; commit or restore it before proving breaks`)
  }
}

const wanted = process.argv.slice(2)
const selected = wanted.length ? BREAKS.filter((b) => wanted.includes(b.name)) : BREAKS
if (wanted.length && selected.length !== wanted.length) {
  console.error(`unknown break(s): ${wanted.filter((w) => !BREAKS.some((b) => b.name === w)).join(', ')}`)
  process.exit(2)
}

gitClean(selected.map((b) => b.file))
const results = []
for (const brk of selected) {
  const file = path.join(FRONTEND, brk.file)
  const original = readFileSync(file, 'utf8')
  const count = original.split(brk.find).length - 1
  if (count !== 1) {
    results.push({ name: brk.name, ok: false, why: `find text matched ${count} times in ${brk.file}` })
    continue
  }
  try {
    writeFileSync(file, original.replace(brk.find, brk.replace))
    let t
    let ran
    if (brk.runner === 'vitest') {
      t = run('vitest', ['run', brk.vitestFile, '-t', brk.grep])
      ran = /Tests\s+.*\d+ (passed|failed)/.test(t.stdout.replace(/\x1b\[[0-9;]*m/g, ''))
    } else {
      build()
      t = run('playwright', ['test', '-c', 'e2e/playwright.config.ts', '-g', escapeRegex(brk.grep), '--reporter=line'])
      ran = /\d+ (passed|failed)/.test(t.stdout)
    }
    const counts = /(\d+) failed/.exec(t.stdout)?.[1]
    brk.detail = counts ? `${counts} failed` : ''
    results.push({
      name: brk.name,
      ok: ran && t.status !== 0,
      why: !ran ? 'no test matched the grep' : t.status !== 0 ? `test failed as required (${brk.detail || 'nonzero exit'})` : 'TEST STILL PASSED',
    })
  } finally {
    writeFileSync(file, original)
  }
}
if (selected.some((b) => b.runner !== 'vitest')) build() // leave a bundle built from the real source
gitClean(selected.map((b) => b.file))

for (const r of results) console.log(`${r.ok ? 'PROVEN ' : 'NOT PROVEN'}  ${r.name}: ${r.why}`)
process.exit(results.every((r) => r.ok) ? 0 : 1)
