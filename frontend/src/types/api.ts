// ─── Run (maps to jobs table) ─────────────────────────────────────────────

export type RunStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'canceled'
  | 'interrupted'

export interface Run {
  id: number
  scope_type: 'file' | 'folder' | 'folder_recursive' | 'path_list'
  scope_paths: string[]
  input_path: string  // legacy fallback
  job_type: string
  status: RunStatus
  queue_position: number | null
  cancel_requested: boolean
  created_at: string
  enqueued_at: string | null
  started_at: string | null
  finished_at: string | null
  log: string | null
  current_phase: string | null
  next_phase_index: number | null
  runner_state: string | null
}

// ─── Stage (maps to job_phases) ──────────────────────────────────────────

export type StageState =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'skipped'

// UI-facing stage codes
export type StageCode =
  | 'indexing'   // Discovery
  | 'metadata'   // Inspection
  | 'scoring'    // Quality Analysis
  | 'culling'    // Similarity Clustering
  | 'keywords'   // Tagging

export const STAGE_DISPLAY: Record<StageCode, { name: string; description: string }> = {
  indexing: { name: 'Discovery', description: 'Scan and register image files' },
  metadata: { name: 'Inspection', description: 'Extract EXIF metadata and generate thumbnails' },
  scoring:  { name: 'Quality Analysis', description: 'AI-powered quality scoring (MUSIQ, LIQE, TOPIQ, Q-Align)' },
  culling:  { name: 'Similarity Clustering', description: 'Group similar images into stacks' },
  keywords: { name: 'Tagging', description: 'Generate keywords and captions via BLIP/CLIP' },
}

export interface Stage {
  phase_order: number
  phase_code: StageCode
  state: StageState
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  // extended from phase status
  items_done?: number
  items_total?: number
  throughput?: number
  eta_seconds?: number
}

// ─── Step (sub-task within a Stage) ─────────────────────────────────────

export type StepState = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'

export interface Step {
  id: number
  step_code: string
  step_name: string
  status: StepState
  started_at: string | null
  completed_at: string | null
  items_done: number
  items_total: number
  throughput_rps: number | null
  error_message: string | null
}

export const STEP_DISPLAY: Record<string, string> = {
  musiq:   'Multi-Scale Quality',
  liqe:    'Learned Quality',
  topiq:   'Top-Down Quality',
  qalign:  'Alignment Quality',
  blip:    'BLIP Captioning',
  clip:    'CLIP Tagging',
}

// ─── Work Item (image being processed) ──────────────────────────────────

export interface WorkItem {
  image_id: number
  image_path: string
  filename: string
  status: 'pending' | 'running' | 'done' | 'skipped' | 'failed'
  duration_ms: number | null
  error: string | null
}

// ─── Scope ───────────────────────────────────────────────────────────────

export interface ScopePreviewResult {
  image_count: number
  folder_count: number
  stage_statuses: Record<StageCode, string>
  stage_counts: Record<StageCode, { done: number; failed: number; skipped: number; total: number }>
}

// ─── Folder tree ─────────────────────────────────────────────────────────

export interface FolderNode {
  path: string
  name: string
  children: FolderNode[]
  phase_statuses?: Record<string, string>
  image_count?: number
}

// ─── Queue entry ─────────────────────────────────────────────────────────

export interface QueueEntry {
  run_id: number
  position: number
  input_path: string
  scope_paths: string[]
  created_at: string
  enqueued_at: string
}

// ─── Image (gallery) ─────────────────────────────────────────────────────

export interface Image {
  id: number
  file_path: string
  filename: string
  folder_path: string
  thumbnail_path: string | null
  rating: number | null
  label: string | null
  musiq_score: number | null
  liqe_score: number | null
  topiq_score: number | null
  qalign_score: number | null
  composite_score: number | null
  keywords: string[]
  caption: string | null
  created_at: string | null
  file_size: number | null
  width: number | null
  height: number | null
  camera_make: string | null
  camera_model: string | null
}

// ─── WebSocket events ────────────────────────────────────────────────────

export interface WsRunProgress {
  type: 'run_progress'
  run_id: number
  stage: string
  step?: string
  items_done: number
  items_total: number
  throughput: number
  eta_seconds: number
}

export interface WsStageTransition {
  type: 'stage_transition'
  run_id: number
  stage: string
  from_state: StageState
  to_state: StageState
}

export interface WsLogLine {
  type: 'log_line'
  run_id: number
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
  message: string
  ts: string
}

export interface WsQueueUpdate {
  type: 'queue_update'
  queue: QueueEntry[]
}

export interface WsWorkItemDone {
  type: 'work_item_done'
  run_id: number
  image_id: number
  stage: string
  status: string
}

export type WsEvent = WsRunProgress | WsStageTransition | WsLogLine | WsQueueUpdate | WsWorkItemDone
