import { api } from './client'
import type { Run, Stage, Step, WorkItem, QueueEntry } from '@/types/api'

export interface RunSubmitRequest {
  scope_type: 'file' | 'folder' | 'folder_recursive' | 'path_list'
  scope_paths: string[]
  stages?: string[]
  skip_done?: boolean
  force_rerun?: boolean
}

export interface RunsListResponse {
  runs: Run[]
  total: number
}

export const runsApi = {
  list: (params?: { status?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams()
    if (params?.status) q.set('status', params.status)
    if (params?.limit != null) q.set('limit', String(params.limit))
    if (params?.offset != null) q.set('offset', String(params.offset))
    const qs = q.toString()
    return api.get<Run[]>(`/jobs/recent?${qs}`)
  },
  get: (id: number) => api.get<Run>(`/jobs/${id}`),
  submit: (body: RunSubmitRequest) => api.post<{ run_id: number; queue_position: number }>('/runs/submit', body),
  pause: (id: number) => api.post<void>(`/runs/${id}/pause`),
  resume: (id: number) => api.post<void>(`/runs/${id}/resume`),
  cancel: (id: number) => api.post<void>(`/runs/${id}/cancel`),
  retry: (id: number) => api.post<void>(`/runs/${id}/retry`),

  getStages: (id: number) => api.get<Stage[]>(`/runs/${id}/stages`),
  retryStage: (id: number, code: string) => api.post<void>(`/runs/${id}/stages/${code}/retry`),
  skipStage: (id: number, code: string) => api.post<void>(`/runs/${id}/stages/${code}/skip`),

  getSteps: (id: number, code: string) => api.get<Step[]>(`/runs/${id}/stages/${code}/steps`),
  getWorkItems: (id: number, code: string, offset = 0, limit = 50) =>
    api.get<{ items: WorkItem[]; total: number }>(`/runs/${id}/stages/${code}/items?offset=${offset}&limit=${limit}`),

  queue: () => api.get<QueueEntry[]>('/queue'),
  reorderQueue: (runId: number, newPosition: number) =>
    api.post<void>('/queue/reorder', { run_id: runId, new_position: newPosition }),
}
