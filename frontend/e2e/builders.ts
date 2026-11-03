/**
 * Fixture builders for the faked backend.
 *
 * Shapes: when openapi.json documents a response schema, the fake api validates every body
 * against it (fixtures.ts). Most endpoints the SPA uses document none (see the contract gaps in
 * docs/guides/UI_E2E_TEST_CATALOG.md); for those, builders are typed with the SPA's own types
 * in src/types/api.ts, so a field the UI does not declare cannot slip in unnoticed.
 */
import type { FolderNode, Run, RunsDriveStatus, Stage } from '../src/types/api'
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

/** Runs shown by default: one running, two finished. */
export const DEFAULT_RUNS: Run[] = [
  run(3, { status: 'running', finished_at: null, current_phase: 'scoring' }),
  run(2, { status: 'completed' }),
  run(1, { status: 'failed', log: 'scoring failed: model not loaded' }),
]

/** Baseline handlers every page needs (the shell's calls), overridable per test. */
export function installBaseline(api: ApiFake, runs: Run[] = DEFAULT_RUNS): void {
  api
    .on('GET', '/api/config', { json: config() })
    .on('GET', '/api/scope/tree', { json: folderTree() })
    .on('GET', '/api/folders/tree', { json: { tree: folderTree(), count: 2 } })
    .on('GET', '/api/runs/drive/status', { json: driveStatus() })
    .on('GET', '/api/jobs/recent', ({ query }) => {
      const statuses = query.get('status')?.split(',')
      const limit = Number(query.get('limit') ?? 50)
      const selected = statuses ? runs.filter((r) => statuses.includes(r.status)) : runs
      return { json: selected.slice(0, limit) }
    })
}
