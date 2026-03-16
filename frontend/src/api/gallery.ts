import { api } from './client'
import type { Image } from '@/types/api'

export interface ImageFilters {
  folder_path?: string
  min_rating?: number
  max_rating?: number
  label?: string
  keyword?: string
  min_score?: number
  max_score?: number
  offset?: number
  limit?: number
}

export interface ImageListResponse {
  images: Image[]
  total: number
  offset: number
  limit: number
}

export interface ImageUpdateRequest {
  rating?: number | null
  label?: string | null
  keywords?: string[]
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
