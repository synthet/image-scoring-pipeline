import { api } from './client'
import type { Image } from '@/types/api'

// Query params matching the legacy /images endpoint
export interface ImageFilters {
  folder_path?: string
  stack_id?: number
  rating?: string         // comma-separated ratings e.g. "3,4,5"
  label?: string          // comma-separated labels e.g. "Pick,Normal"
  keyword?: string
  min_score_general?: number
  min_score_aesthetic?: number
  min_score_technical?: number
  sort_by?: string        // "score" | "score_general" | "date" | "name" | "rating"
  order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export interface ImageListResponse {
  images: Image[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ImageUpdateRequest {
  rating?: number | null
  label?: string | null
  keywords?: string
  title?: string
  description?: string
  write_sidecar?: boolean
}

export const galleryApi = {
  list: (filters: ImageFilters = {}) => {
    const q = new URLSearchParams()
    Object.entries(filters).forEach(([k, v]) => {
      if (v != null) q.set(k, String(v))
    })
    return api.get<ImageListResponse>(`/images?${q.toString()}`)
  },
  get: (id: number) => api.get<Image>(`/images/${id}`),
  update: (id: number, data: ImageUpdateRequest) => api.patch<Image>(`/images/${id}`, data),
  delete: (id: number) => api.delete<void>(`/images/${id}`),
  similar: (id: number, limit = 12) => api.get<Image[]>(`/similar?image_id=${id}&limit=${limit}`),
}
