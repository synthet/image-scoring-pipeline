/**
 * Fixture builders for the faked backend.
 *
 * Shapes: when openapi.json documents a response schema, the fake api validates every body
 * against it (fixtures.ts). Most endpoints the SPA uses document none (see the contract gaps in
 * docs/guides/UI_E2E_TEST_CATALOG.md); for those, builders are typed with the SPA's own types
 * in src/types/api.ts, so a field the UI does not declare cannot slip in unnoticed.
 */
import type {
  FolderNode, Image, ImageAuditlogResponse, ImageDetail, Run, RunFolderBucketsResponse, RunReportResponse, RunsDriveStatus, Stage,
} from '../src/types/api'
import type { FolderDetail, FolderPhaseStatusResponse } from '../src/api/folders'
import type { CullingStacksResponse } from '../src/features/culling/api/culling'
import type { ImageListResponse, NeighborResponse } from '../src/api/gallery'
import type { KeywordCloudResponse } from '../src/api/keywords'
import type { StackAnalytics } from '../src/api/stacks'
import type { LogTailsResponse } from '../src/types/statusLogs'
import type { ApiFake } from './fixtures'

const T0 = Date.parse('2026-10-01T09:00:00Z')
export const iso = (offsetSec: number) => new Date(T0 + offsetSec * 1000).toISOString()

export function config(overrides: Partial<{ embedding_map_enabled: boolean; db_explorer_enabled: boolean; enable_culling: boolean }> = {}) {
  return {
    enable_culling: false,
    embedding_map_enabled: false,
    db_explorer_enabled: true,
    scoring_models: {},
    ...overrides,
  }
}

export function run(id: number, overrides: Partial<Run> = {}): Run {
  return {
    id,
    scope_type: 'folder',
    scope_paths: [`/mnt/d/Photos/2026/2026-10-0${(id % 9) + 1}`],
    input_path: `/mnt/d/Photos/2026/2026-10-0${(id % 9) + 1}`,
    job_type: 'pipeline',
    status: 'completed',
    queue_position: null,
    cancel_requested: false,
    created_at: iso(id * 600),
    enqueued_at: iso(id * 600 + 1),
    started_at: iso(id * 600 + 5),
    finished_at: iso(id * 600 + 300),
    log: null,
    current_phase: null,
    next_phase_index: null,
    runner_state: null,
    queue_payload: null,
    description: null,
    ...overrides,
  }
}

export function stage(order: number, code: Stage['phase_code'], overrides: Partial<Stage> = {}): Stage {
  return {
    phase_order: order,
    phase_code: code,
    state: 'completed',
    started_at: iso(order * 60),
    completed_at: iso(order * 60 + 50),
    error_message: null,
    ...overrides,
  }
}

export function folderTree(): FolderNode[] {
  return [
    {
      path: '/mnt/d/Photos',
      name: 'Photos',
      image_count: 0,
      children: [
        { path: '/mnt/d/Photos/2026', name: '2026', image_count: 120, children: [] },
      ],
    },
  ]
}

export function driveStatus(overrides: Partial<RunsDriveStatus['state']> = {}): RunsDriveStatus {
  return {
    state: {
      enabled: false,
      root_path: null,
      limit: 20,
      max_repeats: 1,
      generate_captions: false,
      target_phases: null,
      started_at: null,
      last_tick_at: 0,
      last_result: null,
      stop_reason: null,
      idle_no_progress_ticks: 0,
      ...overrides,
    },
    outstanding: { total_outstanding: 0, bucket_counts: {}, phase_counts: {} },
  }
}

export function image(id: number, overrides: Partial<Image> = {}): Image {
  return {
    id,
    file_path: `/mnt/d/Photos/2026/2026-10-01/DSC_${String(id).padStart(4, '0')}.NEF`,
    file_name: `DSC_${String(id).padStart(4, '0')}.NEF`,
    folder_id: 1,
    thumbnail_path: `/mnt/d/Photos/.thumbs/${id}.jpg`,
    rating: null,
    label: null,
    keywords: 'bird, heron',
    score_general: Math.round((0.9 - (id % 50) / 100) * 1000) / 1000,
    score_technical: 0.7,
    score_aesthetic: 0.6,
    ...overrides,
  }
}

export function imageDetail(id: number, overrides: Partial<ImageDetail> = {}): ImageDetail {
  return { ...image(id), file_paths: [image(id).file_path], phase_statuses: {}, ...overrides } as ImageDetail
}

export function imageList(images: Image[], page = 1, pageSize = 50): ImageListResponse {
  const start = (page - 1) * pageSize
  return {
    images: images.slice(start, start + pageSize),
    total: images.length,
    page,
    page_size: pageSize,
    total_pages: Math.max(1, Math.ceil(images.length / pageSize)),
  }
}

export function folderDetail(id: number, overrides: Partial<FolderDetail> = {}): FolderDetail {
  return { id, path: '/mnt/d/Photos/2026/2026-10-01', parent_id: null, is_fully_scored: true, image_count: 3, created_at: iso(0), ...overrides }
}

export function stackAnalytics(stackId: number, overrides: Partial<StackAnalytics> = {}): StackAnalytics {
  // modules/culling_analytics/service.py get_stack_analytics: stack_name, best_image_id and
  // member_count are returned but not declared in CullingAnalyticsResponse (see catalog).
  return { scope: 'stack', stack_id: stackId, stack_name: `Stack ${stackId}`, best_image_id: 1, member_count: 3, generated_at: iso(0), ...overrides }
}

export function keywordCloud(kind: 'general' | 'species', words: [string, number][]): KeywordCloudResponse {
  return { kind, keywords: words.map(([w, count]) => ({ keyword_norm: w.toLowerCase(), keyword_display: w, count })) }
}

export function folderBuckets(): RunFolderBucketsResponse {
  return { items: [], total: 0, limit: 20, offset: 0, bucket_counts: {}, phase_counts: {}, target_phases: [] }
}

export function health() {
  return { status: 'healthy', scoring_available: true, tagging_available: true, clustering_available: true }
}

export function diagnostics() {
  return {
    timestamp: iso(0),
    system: { os: 'Linux', os_release: '6.6', python_version: '3.11.9 (main)', cpu_count: 8, memory_total_gb: 32, memory_available_gb: 20, memory_percent: 37 },
    database: { type: 'postgres', path: 'image_scoring', reachable: true, size_mb: 512, last_modified: iso(0) },
    models: { gpu_available: true, cuda_version: '12.4', torch_gpu_name: 'RTX 4060', frameworks: ['torch'] },
    filesystem: { root_dir: '/app', thumbnails_dir: '/app/thumbnails', free_space_gb: 120 },
    config: { debug: false, webui_port: 7860, allowed_paths_count: 2 },
    runners: { scoring: { running: false }, tagging: { running: false } },
  }
}

export function logTails(lines: string[]): LogTailsResponse {
  return { ts: iso(0), lines_requested: 500, sources: [{ id: 'webui', path: '/app/webui.log', exists: true, lines, total_lines: lines.length, error: null }] }
}

/** 1×1 PNG built in memory (no binary fixtures in the repo). */
export const PNG_1PX = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64',
)

/** Every page's own calls on top of the baseline, so any route renders. */
export function installPages(api: ApiFake, images: Image[] = [image(1), image(2), image(3)]): void {
  api
    .on('GET', '/api/runs/{run_id}/stages', { json: [stage(1, 'indexing'), stage(2, 'metadata'), stage(3, 'scoring', { state: 'running', completed_at: null })] })
    .on('GET', '/api/runs/folder-buckets', { json: folderBuckets() })
    .on('GET', '/api/images', ({ query }) => ({ json: imageList(images, Number(query.get('page') ?? 1), Number(query.get('page_size') ?? 50)) }))
    .on('GET', '/api/images/{image_id}', ({ params }) => {
      const id = Number(params.image_id)
      const found = images.find((i) => i.id === id)
      return { json: found ? ({ ...imageDetail(id), ...found } as ImageDetail) : imageDetail(id) }
    })
    .on('GET', '/api/images/{image_id}/neighbors', ({ params }) => {
      const id = Number(params.image_id)
      const neighbors: NeighborResponse = { prev_id: id > 1 ? id - 1 : null, next_id: id < images.length ? id + 1 : null }
      return { json: neighbors }
    })
    .on('GET', '/api/folders/{folder_id}', ({ params }) => ({ json: folderDetail(Number(params.folder_id)) }))
    .on('GET', '/api/analytics/stacks/{stack_id}', ({ params }) => ({ json: stackAnalytics(Number(params.stack_id)) }))
    .on('GET', '/api/keywords/cloud', ({ query }) => ({
      json: query.get('kind') === 'species' ? keywordCloud('species', [['Grey Heron', 12], ['Kingfisher', 4]]) : keywordCloud('general', [['bird', 30], ['water', 8]]),
    }))
    .on('GET', '/api/runs/{run_id}/report', { json: { available: false, reason: 'not_supported' } satisfies RunReportResponse })
    .on('GET', '/api/runs/{run_id}/stages/{stage_code}/steps', { json: [] })
    .on('GET', '/api/images/{image_id}/auditlog', ({ params }) => ({ json: { image_id: Number(params.image_id), items: [] } satisfies ImageAuditlogResponse }))
    .on('GET', '/api/folders/phase-status', ({ query }) => ({
      json: { folder_path: query.get('folder_path') ?? '/mnt/d/Photos/2026/2026-10-01', phases: [] } satisfies FolderPhaseStatusResponse,
    }))
    .on('GET', '/api/stacks', { json: { stacks: [], count: 0 } satisfies CullingStacksResponse })
    .on('GET', '/source-image', { body: PNG_1PX, contentType: 'image/png' })
    .on('GET', '/api/health', { json: health() })
    .on('GET', '/api/diagnostics', { json: diagnostics() })
    .onUndocumented('GET', '/api/status/log-tails', '#770', { json: logTails(['INFO webui started', 'INFO scoring idle']) })
    .onUndocumented('POST', '/api/db/query', '#770', { json: { rows: [], rowcount: 0 } })
}

const TERMINAL: Run['status'][] = ['completed', 'failed', 'canceled', 'interrupted']

type DbRow = Record<string, unknown>

/**
 * POST /api/db/query (undocumented, #770) answered from in-memory tables, by the SQL the DB
 * explorer sends (src/api/db.ts): table list, COUNT(*), SELECT * … LIMIT/OFFSET.
 */
export function dbBackend(api: ApiFake, tables: Record<string, DbRow[]>): void {
  api.onUndocumented('POST', '/api/db/query', '#770', ({ body }) => {
    const sql = String((body as { sql?: string })?.sql ?? '')
    if (/information_schema\.tables/i.test(sql)) {
      return { json: { rows: Object.keys(tables).sort().map((table_name) => ({ table_name })) } }
    }
    const table = /FROM\s+"([^"]+)"/i.exec(sql)?.[1]
    const rows = table ? tables[table] ?? [] : []
    if (/COUNT\(\*\)/i.test(sql)) return { json: { rows: [{ count: rows.length }] } }
    const limit = Number(/LIMIT\s+(\d+)/i.exec(sql)?.[1] ?? rows.length)
    const offset = Number(/OFFSET\s+(\d+)/i.exec(sql)?.[1] ?? 0)
    return { json: { rows: rows.slice(offset, offset + limit), rowcount: rows.length } }
  })
}

/** Runs shown by default: one running (#3), one completed (#2), one failed (#1). Fresh per call. */
export function defaultRuns(): Run[] {
  return [
    run(3, { status: 'running', finished_at: null, current_phase: 'scoring' }),
    run(2, { status: 'completed' }),
    run(1, { status: 'failed', log: 'scoring failed: model not loaded' }),
  ]
}

/** Baseline handlers every page needs (the shell's calls), overridable per test. */
export function installBaseline(api: ApiFake): void {
  api
    .on('GET', '/api/config', { json: config() })
    .on('GET', '/api/scope/tree', { json: folderTree() })
    .on('GET', '/api/folders/tree', { json: { tree: folderTree(), count: 2 } })
    .on('GET', '/api/runs/drive/status', { json: driveStatus() })
  runsBackend(api, defaultRuns())
}

/**
 * A mutable list of runs served by /api/jobs/recent and /api/jobs/{job_id}. Tests change a run's
 * fields to simulate the backend, then push the matching WebSocket event. Returns the list.
 */
export function runsBackend(api: ApiFake, runs: Run[]): Run[] {
  api
    .on('GET', '/api/jobs/{job_id}', ({ params }) => {
      const found = runs.find((r) => r.id === Number(params.job_id))
      return found ? { json: found } : { status: 404, json: { detail: 'Job not found' } }
    })
    // modules/api/routers/tasks.py: always an object {runs, jobs}; with history=true it is
    // terminal jobs only plus `total` (the route docstring still says "JSON array").
    .on('GET', '/api/jobs/recent', ({ query }) => {
      const statuses = query.get('status')?.split(',')
      const limit = Number(query.get('limit') ?? 50)
      const offset = Number(query.get('offset') ?? 0)
      const history = query.get('history') === 'true'
      let selected = statuses ? runs.filter((r) => statuses.includes(r.status)) : runs
      if (history) selected = selected.filter((r) => TERMINAL.includes(r.status))
      const page = selected.slice(offset, offset + limit)
      return { json: history ? { runs: page, jobs: page, total: selected.length } : { runs: page, jobs: page } }
    })
  return runs
}
